"""
REST API Module: HTTP Endpoints for External Integration
Provides REST API for triggering cycles, viewing metrics, and managing the system.
"""
import logging
import traceback
import os
import asyncio
from copy import deepcopy
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks, Query, status, WebSocket, WebSocketDisconnect, Depends, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import json
from datetime import datetime, timedelta
from urllib.parse import parse_qs

from config import load_config, PerceptixConfig
from main import PerceptixSystem
from metrics import MetricsCollector
from exceptions import PerceptixError
from tenancy.tenant_manager import TenantManager
from tenancy.middleware.tenant_resolver import TenantResolver, TenantResolutionError, InvalidTenantError


logger = logging.getLogger("PerceptixAPI")


# -------------------------------------------------------------------------
# Request/Response Models
# -------------------------------------------------------------------------

class TriggerCycleRequest(BaseModel):
    """Request model for triggering a cycle."""
    simulate_failure: bool = Field(default=False, description="Simulate a failure scenario")
    cycle_id: Optional[int] = Field(default=None, description="Optional cycle ID")


class TriggerCycleResponse(BaseModel):
    """Response model for cycle execution."""
    success: bool
    cycle_id: int
    incident_detected: bool
    report_id: Optional[str] = None
    confidence: Optional[float] = None
    message: str


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    timestamp: str
    version: str
    components: Dict[str, str]


class MetricsResponse(BaseModel):
    """Metrics summary response."""
    counters: Dict[str, int]
    gauges: Dict[str, float]
    timers: Dict[str, Dict[str, float]]


class MetaAnalysisResponse(BaseModel):
    """Response model for meta-analysis."""
    period_analyzed: str
    total_incidents: int
    most_frequent_type: str
    detected_pattern: Dict[str, Any]
    recommendation: str


class PlaybookResponse(BaseModel):
    """Response model for a remediation playbook."""
    name: str
    description: str
    steps: int
    triggers: list
    has_rollback: bool


class RemediationApprovalResponse(BaseModel):
    """Response model for pending approvals."""
    token_id: str
    action: str
    details: Dict[str, Any]
    requested_at: str
    expires_at: str


class DashboardSummaryResponse(BaseModel):
    """Aggregated dashboard statistics."""
    total_incidents: int
    active_incidents: int
    critical_incidents: int
    system_health_score: float
    recent_anomalies_count: int
    agent_success_rate: float
    last_cycle_timestamp: Optional[str] = None


class GeminiProofResponse(BaseModel):
    """Runtime proof of Gemini integration for hackathon demos."""
    timestamp: str
    mode: str
    configured_model: str
    provider: str
    api_key_configured: bool
    reasoner_api_available: bool
    reasoning_path: str
    last_reasoning_metadata: Optional[Dict[str, Any]] = None


# -------------------------------------------------------------------------
# Dependencies & State
# -------------------------------------------------------------------------

_initial_config: Optional[PerceptixConfig] = None
_tenant_manager: Optional[TenantManager] = None
_tenant_resolver: Optional[TenantResolver] = None

_tenant_systems: Dict[str, PerceptixSystem] = {}
_tenant_lock: asyncio.Lock = asyncio.Lock()

_websocket_clients_by_tenant: Dict[str, list[WebSocket]] = {}

def _ensure_default_tenant(tenant_manager: TenantManager, tenant_id: str) -> None:
    from tenancy.models.tenant import TenantCreate, TenantConfig
    if tenant_manager.get_tenant(tenant_id):
        return
    tenant_manager.create_tenant(
        TenantCreate(
            id=tenant_id,
            name=f"{tenant_id} (Default)",
            config=TenantConfig(),
            metadata={"system": "auto-created"},
        )
    )

def _build_tenant_config(base: PerceptixConfig, tenant_id: str) -> PerceptixConfig:
    """
    Create a tenant-specific PerceptixConfig with hard isolation via separate SQLite DB.
    """
    cfg = deepcopy(base)

    # Hard isolation: separate DB per tenant.
    tenant_db_dir = Path("data") / "tenants" / tenant_id
    tenant_db_dir.mkdir(parents=True, exist_ok=True)
    cfg.database.type = "sqlite"
    cfg.database.path = str(tenant_db_dir / "perceptix_memory.db")

    # Apply tenant-level settings if the tenant exists.
    if _tenant_manager:
        tenant = _tenant_manager.get_tenant(tenant_id)
    else:
        tenant = None

    if tenant and tenant.config:
        tcfg = tenant.config
        try:
            cfg.system.confidence_threshold = float(tcfg.confidence_threshold)
        except Exception:
            pass
        try:
            cfg.system.max_cycles = int(tcfg.max_cycles)
        except Exception:
            pass

        if tcfg.alert_channels:
            cfg.notification.channels = list(tcfg.alert_channels)
        cfg.notification.enabled = bool(tcfg.enable_notifications)
        cfg.ml.enabled = bool(tcfg.enable_ml)
        cfg.remediation.enabled = bool(tcfg.enable_remediation)

        # Data source wiring (first configured data source).
        if tcfg.data_sources:
            ds = tcfg.data_sources[0]
            ds_type = str(ds.type).lower()
            if ds_type == "sqlite":
                cfg.observer.data_source_type = "sqlite"
                cfg.observer.data_source_path = ds.sqlite_path or ds.database or cfg.observer.data_source_path
            elif ds_type == "bigquery":
                cfg.observer.data_source_type = "bigquery"
                cfg.observer.warehouse_config = {
                    "project_id": ds.bigquery_project_id,
                    "credentials_path": ds.bigquery_credentials_path,
                    "dataset": ds.bigquery_dataset,
                }
            elif ds_type == "snowflake":
                cfg.observer.data_source_type = "snowflake"
                cfg.observer.warehouse_config = {
                    "account": ds.snowflake_account,
                    "user": ds.snowflake_user,
                    "password": ds.snowflake_password,
                    "warehouse": ds.snowflake_warehouse,
                    "database": ds.snowflake_database,
                    "schema": ds.snowflake_schema or "PUBLIC",
                    "role": ds.snowflake_role or "SYSADMIN",
                }

        # Optional per-tenant table config.
        custom = dict(getattr(tcfg, "custom_settings", {}) or {})
        monitored = custom.get("monitored_tables")
        if isinstance(monitored, list) and monitored:
            cfg.observer.monitored_tables = [str(x) for x in monitored if str(x).strip()]
            # If BigQuery dataset is set and tables are bare names, prefix them.
            dataset = str(cfg.observer.warehouse_config.get("dataset") or "").strip() if isinstance(cfg.observer.warehouse_config, dict) else ""
            if cfg.observer.data_source_type == "bigquery" and dataset:
                prefixed = []
                for t in cfg.observer.monitored_tables:
                    prefixed.append(t if "." in t else f"{dataset}.{t}")
                cfg.observer.monitored_tables = prefixed

        ts_cols = custom.get("table_timestamp_columns")
        if isinstance(ts_cols, dict):
            cfg.observer.table_timestamp_columns = {str(k): str(v) for k, v in ts_cols.items() if v is not None}

        null_cols = custom.get("table_null_columns")
        if isinstance(null_cols, dict):
            cfg.observer.table_null_columns = {
                str(k): [str(c) for c in (v or []) if str(c).strip()]
                for k, v in null_cols.items()
            }

    return cfg

def get_tenant_id(request: Request) -> str:
    if not _tenant_resolver:
        return "demo"
    try:
        tenant_id = _tenant_resolver.resolve_tenant(request)
        if not tenant_id:
            return "demo"
        return tenant_id
    except (TenantResolutionError, InvalidTenantError):
        # Default to demo unless strict tenancy is enabled.
        if _initial_config and _initial_config.tenancy.require_tenant_header:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or missing tenant")
        return (_initial_config.tenancy.default_tenant if _initial_config and _initial_config.tenancy.default_tenant else "demo")

def _get_tenant_manager() -> TenantManager:
    global _tenant_manager
    if _tenant_manager:
        return _tenant_manager
    cfg = load_config()
    _tenant_manager = TenantManager(db_path=cfg.tenancy.tenant_db_path if cfg.tenancy else "perceptix_tenants.db")
    return _tenant_manager

async def get_system(request: Request) -> PerceptixSystem:
    """Dependency to get the tenant-scoped PerceptixSystem instance."""
    tenant_id = get_tenant_id(request)

    # Fast path
    system = _tenant_systems.get(tenant_id)
    if system:
        return system

    async with _tenant_lock:
        system = _tenant_systems.get(tenant_id)
        if system:
            return system

        if _initial_config is None:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="System not initialized")

        tenant_cfg = _build_tenant_config(_initial_config, tenant_id)
        system = PerceptixSystem(tenant_cfg, tenant_id=tenant_id)
        _tenant_systems[tenant_id] = system
        _websocket_clients_by_tenant.setdefault(tenant_id, [])
        return system


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown.

    This replaces the deprecated @app.on_event decorators.
    """
    global _tenant_manager, _tenant_resolver, _initial_config

    # Startup
    logger.info("Starting Perceptix API...")
    try:
        config = load_config()
        _initial_config = config

        # Tenancy bootstrapping (always enabled with safe defaults).
        tenant_db_path = config.tenancy.tenant_db_path if config.tenancy else "perceptix_tenants.db"
        _tenant_manager = TenantManager(db_path=tenant_db_path)
        default_tenant = config.tenancy.default_tenant if config.tenancy and config.tenancy.default_tenant else "demo"
        _ensure_default_tenant(_tenant_manager, default_tenant)
        _tenant_resolver = TenantResolver(
            tenant_manager=_tenant_manager,
            require_tenant=bool(config.tenancy.require_tenant_header) if config.tenancy else False,
            default_tenant=default_tenant,
        )

        # Initialize default tenant system so health endpoints show "up".
        default_cfg = _build_tenant_config(config, default_tenant)
        _tenant_systems[default_tenant] = PerceptixSystem(default_cfg, tenant_id=default_tenant)
        _websocket_clients_by_tenant.setdefault(default_tenant, [])
        logger.info("Perceptix API started successfully")
    except Exception as e:
        logger.critical(f"Failed to start Perceptix System: {e}")
        raise

    # Notify systemd only when running under a systemd NOTIFY_SOCKET.
    if os.getenv("NOTIFY_SOCKET"):
        try:
            import sdnotify
            notifier = sdnotify.SystemdNotifier()
            notifier.notify("READY=1")
            logger.info("Sent READY=1 notification to systemd")
        except Exception as e:
            logger.debug(f"Could not notify systemd: {e}")

    yield

    # Shutdown
    logger.info("Shutting down Perceptix API...")
    for system in list(_tenant_systems.values()):
        try:
            system.shutdown()
        except Exception:
            pass
    logger.info("Perceptix API shutdown complete")


# -------------------------------------------------------------------------
# FastAPI Application
# -------------------------------------------------------------------------

app = FastAPI(
    title="Perceptix API",
    description="REST API for Perceptix Autonomous Data Reliability Agent",
    version="1.0.0",
    lifespan=lifespan
)

# Load config for middleware setup
_initial_config = load_config()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=_initial_config.api.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -------------------------------------------------------------------------
# Health Check Endpoints
# -------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """
    Liveness probe - checks if the API is running.

    Returns:
        HealthResponse: Health status
    """
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now().isoformat(),
        version="1.0.0",
        components={
            "api": "up",
            "system": "up" if _tenant_systems else "down"
        }
    )


@app.get("/health/ready", response_model=HealthResponse, tags=["Health"])
async def readiness_check(system: PerceptixSystem = Depends(get_system)):
    """
    Readiness probe - checks if the system is ready to handle requests.

    Returns:
        HealthResponse: Readiness status

    Raises:
        HTTPException: If system is not ready
    """
    # Check database connectivity
    try:
        with system.db_manager.connection() as conn:
            conn.execute("SELECT 1").fetchone()
    except Exception as e:
        logger.error(f"Database check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database not ready: {str(e)}"
        )

    return HealthResponse(
        status="ready",
        timestamp=datetime.now().isoformat(),
        version="1.0.0",
        components={
            "api": "ready",
            "system": "ready",
            "database": "ready"
        }
    )


# -------------------------------------------------------------------------
# Authentication Endpoints
# -------------------------------------------------------------------------

from auth import Token, TokenData, create_access_token, get_current_user, verify_password, get_password_hash
from config import load_config

def require_admin(current_user: TokenData = Depends(get_current_user)) -> TokenData:
    """RBAC-lite: only allow configured admin users to access admin endpoints."""
    config = load_config()
    if current_user.is_admin or (current_user.username in (config.api.admin_users or [])):
        return current_user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin privileges required",
    )

@app.post("/api/v1/auth/token", response_model=Token, tags=["Authentication"])
async def login_for_access_token(request: Request):
    """
    Get an access token (Login).
    
    For a real system, you'd check a user database.
    For demo mode, credentials are loaded from config/environment.
    """
    content_type = request.headers.get("content-type", "")
    username = None
    password = None

    if "application/json" in content_type:
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        username = payload.get("username")
        password = payload.get("password")
    else:
        # Support x-www-form-urlencoded without requiring python-multipart.
        body = (await request.body()).decode("utf-8")
        form = parse_qs(body)
        username = form.get("username", [None])[0]
        password = form.get("password", [None])[0]

    if not username or not password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="username and password are required",
        )

    # DEMO AUTHENTICATION
    # For hackathon/demo mode, credentials come from environment-backed config.
    config = load_config()
    if (
        username != config.api.demo_username
        or password != config.api.demo_password
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Create token
    access_token_expires = timedelta(minutes=30)
    is_admin = username in (config.api.admin_users or [])
    access_token = create_access_token(
        data={"sub": username, "adm": is_admin},
        expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


# -------------------------------------------------------------------------
# Cycle Management Endpoints
# -------------------------------------------------------------------------

@app.post("/api/v1/cycles/trigger", response_model=TriggerCycleResponse, tags=["Cycles"])
async def trigger_cycle(
    request: TriggerCycleRequest, 
    background_tasks: BackgroundTasks,
    system: PerceptixSystem = Depends(get_system),
    current_user: TokenData = Depends(get_current_user)
):
    """
    Trigger a new analysis cycle.

    Args:
        request: Cycle trigger request
        background_tasks: FastAPI background tasks

    Returns:
        TriggerCycleResponse: Cycle execution result
    """
    try:
        import asyncio

        async def _run_cycle_and_broadcast() -> None:
            tenant_id = getattr(system, "tenant_id", None)
            try:
                report = await system.run_cycle(
                    cycle_id=cycle_id,
                    simulate_failure=request.simulate_failure,
                )

                if report:
                    await broadcast_to_websockets(
                        {
                            "type": "incident_detected",
                            "data": {
                                "cycle_id": cycle_id,
                                "report_id": report.report_id,
                                "incident_type": report.incident_type.value,
                                "confidence": report.final_confidence_score,
                                "message": f"Incident detected: {report.incident_type.value}",
                            },
                            "timestamp": datetime.now().isoformat(),
                        },
                        tenant_id=tenant_id,
                    )
                else:
                    await broadcast_to_websockets(
                        {
                            "type": "cycle_completed",
                            "data": {
                                "cycle_id": cycle_id,
                                "incident_detected": False,
                                "message": "No anomalies detected - system healthy",
                            },
                            "timestamp": datetime.now().isoformat(),
                        },
                        tenant_id=tenant_id,
                    )
            except Exception as e:
                logger.error(f"Unexpected error during cycle background task: {e}")
                logger.error(traceback.format_exc())
                await broadcast_to_websockets(
                    {
                        "type": "cycle_error",
                        "data": {
                            "message": str(e),
                            "component": "api.trigger_cycle.background",
                        },
                        "timestamp": datetime.now().isoformat(),
                    },
                    tenant_id=tenant_id,
                )

        # Increment cycle counter
        system.cycle_count += 1
        cycle_id = request.cycle_id or system.cycle_count

        logger.info(f"API triggered cycle {cycle_id}, simulate_failure={request.simulate_failure}")
        await broadcast_to_websockets(
            {
                "type": "cycle_started",
                "data": {
                    "cycle_id": cycle_id,
                    "simulate_failure": request.simulate_failure,
                    "triggered_by": current_user.username,
                },
                "timestamp": datetime.now().isoformat(),
            },
            tenant_id=getattr(system, "tenant_id", None),
        )

        # Run asynchronously so nginx/frontends don't hit upstream timeouts.
        asyncio.create_task(_run_cycle_and_broadcast())

        return TriggerCycleResponse(
            success=True,
            cycle_id=cycle_id,
            incident_detected=False,
            message="Cycle started",
        )

    except PerceptixError as e:
        logger.error(f"Perceptix error during cycle: {e}")
        await broadcast_to_websockets({
            "type": "cycle_error",
            "data": {
                "message": e.message,
                "component": e.component,
            },
            "timestamp": datetime.now().isoformat(),
        }, tenant_id=getattr(system, "tenant_id", None))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Cycle execution failed: {e.message}"
        )
    except Exception as e:
        logger.error(f"Unexpected error during cycle: {e}")
        logger.error(traceback.format_exc())
        await broadcast_to_websockets({
            "type": "cycle_error",
            "data": {
                "message": str(e),
                "component": "api.trigger_cycle",
            },
            "timestamp": datetime.now().isoformat(),
        }, tenant_id=getattr(system, "tenant_id", None))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {str(e)}"
        )


@app.get("/api/v1/cycles/status", tags=["Cycles"])
async def get_cycle_status(system: PerceptixSystem = Depends(get_system)):
    """
    Get current cycle execution status.

    Returns:
        Dict: Cycle status information
    """
    return {
        "total_cycles": system.cycle_count,
        "max_cycles": system.config.system.max_cycles,
        "system_mode": system.config.system.mode.value
    }


# -------------------------------------------------------------------------
# Metrics Endpoints
# -------------------------------------------------------------------------

def _sum_counter_variants(counters: Dict[str, int], base_name: str) -> int:
    """
    Sum a metric counter across tagged and untagged variants.

    Example:
        base_name='agent_execution_count' will sum:
        - agent_execution_count
        - agent_execution_count[agent=observer]
        - agent_execution_count[agent=reasoner]
    """
    total = 0
    for key, value in counters.items():
        if key == base_name or key.startswith(f"{base_name}["):
            total += int(value)
    return total


@app.get("/api/v1/metrics", response_model=MetricsResponse, tags=["Metrics"])
async def get_metrics(system: PerceptixSystem = Depends(get_system)):
    """
    Get system metrics summary.

    Returns:
        MetricsResponse: Metrics summary
    """
    summary = system.get_metrics_summary()
    counters = dict(summary.get("counters", {}))
    gauges = dict(summary.get("gauges", {}))

    # Normalize key counters for dashboard/chart compatibility.
    counters["alerts_sent"] = counters.get("alerts_total", 0)
    counters["alerts_critical"] = (
        counters.get("alerts_critical", 0)
        + counters.get("alert_level_CRITICAL", 0)
    )
    counters["alerts_warning"] = (
        counters.get("alerts_warning", 0)
        + counters.get("alert_level_WARNING", 0)
    )
    counters["agent_execution_count"] = _sum_counter_variants(counters, "agent_execution_count")
    counters["agent_success_count"] = _sum_counter_variants(counters, "agent_success_count")
    counters["agent_failure_count"] = _sum_counter_variants(counters, "agent_failure_count")

    # Backfill confidence summary gauges from recent incidents if missing.
    if (
        "confidence_avg" not in gauges
        or "confidence_min" not in gauges
        or "confidence_max" not in gauges
    ):
        recent_incidents = system.historian.get_recent_incidents(limit=200, include_archived=True)
        confidence_values = [float(inc[3]) for inc in recent_incidents if inc and inc[3] is not None]
        if confidence_values:
            gauges["confidence_avg"] = sum(confidence_values) / len(confidence_values)
            gauges["confidence_min"] = min(confidence_values)
            gauges["confidence_max"] = max(confidence_values)
        else:
            gauges.setdefault("confidence_avg", 0.0)
            gauges.setdefault("confidence_min", 0.0)
            gauges.setdefault("confidence_max", 0.0)

    return MetricsResponse(
        counters=counters,
        gauges=gauges,
        timers=summary.get("timers", {})
    )


@app.get("/metrics", response_class=PlainTextResponse, tags=["Metrics"])
async def prometheus_metrics():
    """
    Prometheus-compatible metrics endpoint.

    Returns:
        str: Metrics in Prometheus format
    """
    collector = MetricsCollector()
    return collector.export_prometheus()


# -------------------------------------------------------------------------
# Incident Management Endpoints
# -------------------------------------------------------------------------

class IncidentBulkActionRequest(BaseModel):
    """Request model for bulk incident actions."""
    incident_ids: list[str] = Field(min_length=1, max_length=200)

@app.get("/api/v1/incidents", tags=["Incidents"])
async def get_incidents(
    limit: int = Query(default=10, ge=1, le=100, description="Number of incidents to retrieve"),
    incident_type: Optional[str] = Query(default=None, description="Filter by incident type"),
    confidence_min: Optional[float] = Query(default=None, ge=0.0, le=100.0, description="Minimum confidence score"),
    after: Optional[str] = Query(default=None, description="Retrieve incidents after this timestamp"),
    include_archived: bool = Query(default=False, description="Include archived incidents"),
    status_filter: Optional[str] = Query(default=None, description="Filter by incident status"),
    system: PerceptixSystem = Depends(get_system)
):
    """
    Get recent incidents from database with filtering options.

    Args:
        limit: Number of incidents to retrieve (1-100)
        incident_type: Optional type filter
        confidence_min: Optional minimum confidence filter
        after: Optional timestamp filter (ISO format)

    Returns:
        Dict: List of recent incidents
    """
    try:
        incidents = system.historian.get_recent_incidents(
            limit=limit,
            incident_type=incident_type,
            confidence_min=confidence_min,
            timestamp_after=after,
            include_archived=(include_archived or status_filter == "ARCHIVED"),
            status=status_filter,
        )

        return {
            "count": len(incidents),
            "incidents": [
                {
                    "id": inc[0],
                    "timestamp": inc[1],
                    "type": inc[2],
                    "confidence": inc[3],
                    "status": inc[4],
                    "summary": inc[5]
                }
                for inc in incidents
            ]
        }
    except Exception as e:
        logger.error(f"Failed to retrieve incidents: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve incidents: {str(e)}"
        )


@app.get("/api/v1/incidents/{report_id}", tags=["Incidents"])
async def get_incident_by_id(
    report_id: str,
    system: PerceptixSystem = Depends(get_system)
):
    """
    Get a specific incident by report ID.

    Args:
        report_id: Report ID to retrieve

    Returns:
        Dict: Incident details
    """
    try:
        with system.db_manager.connection() as conn:
            cursor = conn.execute(
                "SELECT id, timestamp, type, confidence, summary, full_json FROM incidents WHERE id = ?",
                (report_id,)
            )
            incident = cursor.fetchone()

        if not incident:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Incident {report_id} not found"
            )

        import json
        full_data = json.loads(incident[5])

        return {
            "id": incident[0],
            "timestamp": incident[1],
            "type": incident[2],
            "confidence": incident[3],
            "summary": incident[4],
            "details": full_data
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve incident {report_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve incident: {str(e)}"
        )


@app.post("/api/v1/incidents/{report_id}/archive", tags=["Incidents"])
async def archive_incident(
    report_id: str,
    system: PerceptixSystem = Depends(get_system),
    current_user: TokenData = Depends(get_current_user)
):
    """Archive a single incident."""
    try:
        archived = system.historian.archive_incident(report_id)
        if not archived:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Incident {report_id} not found or already archived"
            )

        system.historian.record_audit_event(
            actor=current_user.username or "unknown",
            action="incident.archive",
            entity_type="incident",
            entity_id=report_id,
            details={"mode": "single"},
        )
        logger.info(f"Incident archived: {report_id}")
        return {"success": True, "report_id": report_id, "action": "archived"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to archive incident {report_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to archive incident: {str(e)}"
        )


@app.delete("/api/v1/incidents/{report_id}", tags=["Incidents"])
async def delete_incident(
    report_id: str,
    system: PerceptixSystem = Depends(get_system),
    current_user: TokenData = Depends(get_current_user)
):
    """Permanently delete a single incident."""
    try:
        deleted = system.historian.delete_incident(report_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Incident {report_id} not found"
            )

        system.historian.record_audit_event(
            actor=current_user.username or "unknown",
            action="incident.delete",
            entity_type="incident",
            entity_id=report_id,
            details={"mode": "single"},
        )
        logger.warning(f"Incident deleted: {report_id}")
        return {"success": True, "report_id": report_id, "action": "deleted"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete incident {report_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete incident: {str(e)}"
        )


@app.post("/api/v1/incidents/bulk/archive", tags=["Incidents"])
async def bulk_archive_incidents(
    request: IncidentBulkActionRequest,
    system: PerceptixSystem = Depends(get_system),
    current_user: TokenData = Depends(get_current_user)
):
    """Archive multiple incidents."""
    try:
        affected = system.historian.bulk_archive_incidents(request.incident_ids)
        system.historian.record_audit_event(
            actor=current_user.username or "unknown",
            action="incident.archive",
            entity_type="incident",
            entity_id=None,
            details={"mode": "bulk", "requested_count": len(request.incident_ids), "affected_count": affected},
        )
        logger.info(
            f"Bulk archive complete: requested={len(request.incident_ids)}, affected={affected}"
        )
        return {
            "success": True,
            "action": "archived",
            "requested_count": len(request.incident_ids),
            "affected_count": affected,
        }
    except Exception as e:
        logger.error(f"Failed bulk archive: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to archive incidents: {str(e)}"
        )


@app.post("/api/v1/incidents/bulk/delete", tags=["Incidents"])
async def bulk_delete_incidents(
    request: IncidentBulkActionRequest,
    system: PerceptixSystem = Depends(get_system),
    current_user: TokenData = Depends(get_current_user)
):
    """Permanently delete multiple incidents."""
    try:
        affected = system.historian.bulk_delete_incidents(request.incident_ids)
        system.historian.record_audit_event(
            actor=current_user.username or "unknown",
            action="incident.delete",
            entity_type="incident",
            entity_id=None,
            details={"mode": "bulk", "requested_count": len(request.incident_ids), "affected_count": affected},
        )
        logger.warning(
            f"Bulk delete complete: requested={len(request.incident_ids)}, affected={affected}"
        )
        return {
            "success": True,
            "action": "deleted",
            "requested_count": len(request.incident_ids),
            "affected_count": affected,
        }
    except Exception as e:
        logger.error(f"Failed bulk delete: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete incidents: {str(e)}"
        )


@app.get("/api/v1/dashboard/summary", response_model=DashboardSummaryResponse, tags=["Dashboard"])
async def get_dashboard_summary(system: PerceptixSystem = Depends(get_system)):
    """
    Get aggregated dashboard summary statistics.

    Returns:
        DashboardSummaryResponse: Aggregated statistics
    """
    try:
        metrics = system.get_metrics_summary()
        counters = metrics.get("counters", {})

        # Calculate health score (0-100)
        # Based on incident count and error rates in recent metrics
        total_cycles = counters.get("cycles_total", 0)
        anomalies = counters.get("anomalies_detected", 0)
        errors = counters.get("errors_total", 0)
        
        health_score = 100.0
        if total_cycles > 0:
            anomaly_rate = anomalies / total_cycles
            health_score -= (anomaly_rate * 50.0) # Anomaly rate up to 50% impact
        
        if errors > 0:
            health_score -= min(30.0, errors * 2.0) # Errors up to 30% impact

        health_score = max(0.0, health_score)

        # Get database-backed incident statistics (not capped in-memory samples).
        active_cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
        incident_stats = system.historian.get_incident_statistics(
            active_since=active_cutoff,
            include_archived=False,
        )
        total_incidents = incident_stats.get("total", 0)
        active_incidents = incident_stats.get("active", 0)
        critical_count = incident_stats.get("critical", 0)

        # Calculate agent success rate from tagged + untagged counters.
        agent_success = _sum_counter_variants(counters, "agent_success_count")
        agent_total = _sum_counter_variants(counters, "agent_execution_count")
        success_rate = (agent_success / agent_total * 100.0) if agent_total > 0 else 100.0

        return DashboardSummaryResponse(
            total_incidents=total_incidents,
            active_incidents=active_incidents,
            critical_incidents=critical_count,
            system_health_score=health_score,
            recent_anomalies_count=anomalies,
            agent_success_rate=success_rate,
            last_cycle_timestamp=system.last_cycle_timestamp
        )
    except Exception as e:
        logger.error(f"Failed to generate dashboard summary: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate dashboard summary: {str(e)}"
        )


@app.get("/api/v1/dashboard/trends", tags=["Dashboard"])
async def get_dashboard_trends(
    days: int = Query(default=7, ge=1, le=90, description="Number of days to include in trend window"),
    system: PerceptixSystem = Depends(get_system),
):
    """Return incident trends and MTTR statistics based on persisted incidents."""
    try:
        return system.historian.get_dashboard_trends(days=days)
    except Exception as e:
        logger.error(f"Failed to generate dashboard trends: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate dashboard trends: {str(e)}"
        )


# -------------------------------------------------------------------------
# Configuration Endpoints
# -------------------------------------------------------------------------

@app.get("/api/v1/hackathon/gemini-proof", response_model=GeminiProofResponse, tags=["Hackathon"])
async def get_gemini_proof(system: PerceptixSystem = Depends(get_system)):
    """
    Return verifiable Gemini runtime details for judges and demo reviewers.

    This endpoint intentionally avoids secrets and only exposes safe metadata.
    """
    reasoner_api_available = bool(system.reasoner.api_available and system.reasoner.client is not None)

    return GeminiProofResponse(
        timestamp=datetime.now().isoformat(),
        mode=system.config.system.mode.value,
        configured_model=system.config.api.model_name,
        provider="google-genai",
        api_key_configured=bool(system.config.api.gemini_api_key),
        reasoner_api_available=reasoner_api_available,
        reasoning_path="api" if reasoner_api_available else "mock",
        last_reasoning_metadata=system.last_reasoning_metadata
    )

@app.get("/api/v1/config", tags=["Configuration"])
async def get_configuration(system: PerceptixSystem = Depends(get_system)):
    """
    Get current system configuration (sanitized).

    Returns:
        Dict: System configuration (without secrets)
    """
    config = system.config
    visible_channels = [
        channel for channel in config.notification.channels
        if channel.lower() != "pagerduty"
    ]

    return {
        "system": {
            "mode": config.system.mode.value,
            "confidence_threshold": config.system.confidence_threshold,
            "max_cycles": config.system.max_cycles
        },
        "notification": {
            "channels": visible_channels,
            "slack_configured": bool(config.notification.slack_webhook_url),
            "email_configured": bool(
                config.notification.email_smtp_host
                and config.notification.email_from
                and config.notification.email_to
            )
        },
        "database": {
            "path": config.database.path,
            "max_connections": config.database.max_connections
        }
    }


# -------------------------------------------------------------------------
# Error Handlers
# -------------------------------------------------------------------------

@app.exception_handler(PerceptixError)
async def cognizant_error_handler(request, exc: PerceptixError):
    """Handle PerceptixError exceptions."""
    logger.error(f"PerceptixError: {exc.to_dict()}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "PerceptixError",
            "message": exc.message,
            "component": exc.component,
            "trace_id": exc.trace_id
        }
    )


@app.exception_handler(Exception)
async def general_error_handler(request, exc: Exception):
    """Handle unexpected exceptions."""
    logger.error(f"Unexpected error: {exc}")
    logger.error(traceback.format_exc())
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "InternalServerError",
            "message": str(exc)
        }
    )


# -------------------------------------------------------------------------
# WebSocket Endpoints
# -------------------------------------------------------------------------

@app.websocket("/ws/incidents")
async def websocket_incidents(websocket: WebSocket):
    """
    WebSocket endpoint for real-time incident updates.

    Clients can connect to this endpoint to receive real-time notifications
    about new incidents and system events.
    """
    await websocket.accept()
    tenant_id = (
        websocket.query_params.get("tenant_id")
        or websocket.headers.get("x-tenant-id")
        or websocket.headers.get("X-Tenant-ID")
        or (
            _initial_config.tenancy.default_tenant
            if _initial_config and _initial_config.tenancy and _initial_config.tenancy.default_tenant
            else "demo"
        )
    )
    _websocket_clients_by_tenant.setdefault(tenant_id, []).append(websocket)

    try:
        logger.info("WebSocket client connected (tenant=%s)", tenant_id)

        # Send welcome message
        await websocket.send_json({
            "type": "system_status",
            "data": {"status": "connected", "message": "Connected to Perceptix incident stream"},
            "timestamp": datetime.now().isoformat()
        })

        # Keep connection alive
        while True:
            # Wait for any client messages (ping/pong)
            try:
                data = await websocket.receive_text()
                # Echo back to confirm connection
                await websocket.send_json({
                    "type": "system_status",
                    "data": {"status": "alive"},
                    "timestamp": datetime.now().isoformat()
                })
            except WebSocketDisconnect:
                break

    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        logger.info("WebSocket client disconnected (tenant=%s)", tenant_id)
        clients = _websocket_clients_by_tenant.get(tenant_id, [])
        if websocket in clients:
            clients.remove(websocket)


async def broadcast_to_websockets(message: Dict[str, Any], tenant_id: str | None = None):
    """
    Broadcast a message to all connected WebSocket clients.

    Args:
        message: Message to broadcast
        tenant_id: If set, only broadcast to that tenant.
    """
    disconnected_clients: list[tuple[str, WebSocket]] = []

    targets: Dict[str, list[WebSocket]]
    if tenant_id:
        targets = {tenant_id: _websocket_clients_by_tenant.get(tenant_id, [])}
    else:
        targets = dict(_websocket_clients_by_tenant)

    for t_id, clients in targets.items():
        for client in list(clients):
            try:
                await client.send_json(message)
            except Exception as e:
                logger.error(f"Failed to send WebSocket message: {e}")
                disconnected_clients.append((t_id, client))

    # Remove disconnected clients
    for t_id, client in disconnected_clients:
        clients = _websocket_clients_by_tenant.get(t_id, [])
        if client in clients:
            clients.remove(client)


# -------------------------------------------------------------------------
# Time Series Metrics Endpoint
# -------------------------------------------------------------------------

class TimeSeriesDataPoint(BaseModel):
    """Single data point in a time series."""
    timestamp: str
    value: float


class TimeSeriesMetrics(BaseModel):
    """Time series metrics response."""
    metric: str
    data: list[TimeSeriesDataPoint]
    start_time: str
    end_time: str


@app.get("/api/v1/metrics/timeseries", response_model=TimeSeriesMetrics, tags=["Metrics"])
async def get_metrics_timeseries(
    start_time: str = Query(..., description="Start time in ISO format"),
    end_time: str = Query(..., description="End time in ISO format"),
    metric: str = Query(..., description="Metric name (cycles, confidence, alerts)"),
    system: PerceptixSystem = Depends(get_system)
):
    """
    Get time-series metrics data for visualization.

    Args:
        start_time: Start time for the time series
        end_time: End time for the time series
        metric: Metric type to retrieve

    Returns:
        TimeSeriesMetrics: Time series data

    Note:
        This is a simplified implementation. In production, you would query
        a time-series database or metrics store.
    """
    try:
        # Query metrics from database
        query = """
            SELECT timestamp, value 
            FROM metrics_timeseries 
            WHERE metric_name = ? 
            AND timestamp BETWEEN ? AND ?
            ORDER BY timestamp ASC
        """
        
        with system.db_manager.connection() as conn:
            cursor = conn.execute(query, (metric, start_time, end_time))
            rows = cursor.fetchall()
            
        data_points = [
            TimeSeriesDataPoint(timestamp=row[0], value=row[1]) 
            for row in rows
        ]

        return TimeSeriesMetrics(
            metric=metric,
            data=data_points,
            start_time=start_time,
            end_time=end_time
        )

    except Exception as e:
        logger.error(f"Failed to retrieve time series metrics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve time series metrics: {str(e)}"
        )


# -------------------------------------------------------------------------
# ML PREDICTION ENDPOINTS
# -------------------------------------------------------------------------

class MLPredictionRequest(BaseModel):
    """Request model for ML prediction."""
    table_name: str = Field(..., description="Name of the table to analyze")
    row_count: int = Field(..., ge=0, description="Current row count")
    freshness_minutes: int = Field(..., ge=0, description="Freshness in minutes")
    null_rates: Dict[str, float] = Field(..., description="Null rates per column")


class MLPredictionResponse(BaseModel):
    """Response model for ML prediction."""
    table_name: str
    is_anomaly: bool
    anomaly_score: float
    confidence: float
    model_scores: Dict[str, float]
    timestamp: str
    models_used: list[str]


class MLModelInfoResponse(BaseModel):
    """Response model for ML model information."""
    enabled: bool
    models_trained: bool
    models_available: list[str]
    training_date: Optional[str] = None
    training_samples: int = 0


@app.post("/api/v1/ml/predict", response_model=MLPredictionResponse, tags=["ML"])
async def predict_anomaly(
    request: MLPredictionRequest,
    system: PerceptixSystem = Depends(get_system),
    current_user: TokenData = Depends(get_current_user)
):
    """
    Predict if a table metric is anomalous using ML models.

    Args:
        request: Table metrics to analyze

    Returns:
        MLPredictionResponse: ML prediction results

    Raises:
        HTTPException: If ML is not enabled or prediction fails
    """
    try:
        # Check if ML is enabled
        config = system.config
        if not config.ml.enabled:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="ML anomaly detection is not enabled"
            )

        # Import ML detector
        from ml.ml_anomaly_detector import MLAnomalyDetector
        from models import TableMetric

        # Get or create ML detector
        # Storing on system instance instead of app_state dict
        if not hasattr(system, "ml_detector"):
            ml_detector = MLAnomalyDetector(
                models_dir=config.ml.models_dir,
                enable_isolation_forest=config.ml.enable_isolation_forest,
                enable_autoencoder=config.ml.enable_autoencoder,
                enable_forecaster=config.ml.enable_forecaster
            )
            system.ml_detector = ml_detector
        else:
            ml_detector = system.ml_detector

        # Check if models are trained
        if not ml_detector.is_trained:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="ML models are not trained. Please train models first."
            )

        # Create TableMetric object
        metric = TableMetric(
            row_count=request.row_count,
            freshness_minutes=request.freshness_minutes,
            null_rates=request.null_rates,
            table_name=request.table_name,
            timestamp=datetime.now()
        )

        # Get prediction
        prediction = ml_detector.predict(metric)

        # Build response
        models_used = list(prediction.model_scores.keys())

        return MLPredictionResponse(
            table_name=request.table_name,
            is_anomaly=prediction.is_anomaly,
            anomaly_score=float(prediction.anomaly_score),
            confidence=float(prediction.confidence),
            model_scores={k: float(v) for k, v in prediction.model_scores.items()},
            timestamp=prediction.timestamp.isoformat(),
            models_used=models_used
        )

    except HTTPException:
        raise
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="ML modules not available"
        )
    except Exception as e:
        logger.error(f"ML prediction failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"ML prediction failed: {str(e)}"
        )


@app.get("/api/v1/ml/info", response_model=MLModelInfoResponse, tags=["ML"])
async def get_ml_info(system: PerceptixSystem = Depends(get_system)):
    """
    Get information about ML model status and availability.

    Returns:
        MLModelInfoResponse: ML model information
    """
    try:
        config = system.config

        # If ML not enabled
        if not config.ml.enabled:
            return MLModelInfoResponse(
                enabled=False,
                models_trained=False,
                models_available=[],
                training_samples=0
            )

        # Try to get ML detector status
        if hasattr(system, "ml_detector"):
            ml_detector = system.ml_detector
            model_info = ml_detector.get_model_info()

            return MLModelInfoResponse(
                enabled=True,
                models_trained=ml_detector.is_trained,
                models_available=model_info.get('models_trained', []),
                training_date=model_info.get('training_date'),
                training_samples=model_info.get('training_samples', 0)
            )
        else:
            # ML enabled but not initialized yet
            return MLModelInfoResponse(
                enabled=True,
                models_trained=False,
                models_available=[],
                training_samples=0
            )

    except Exception as e:
        logger.error(f"Failed to get ML info: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve ML information: {str(e)}"
        )


# -------------------------------------------------------------------------
# Tenant Management Endpoints (Phase 10: Multi-Tenancy)
# -------------------------------------------------------------------------

class TenantCreateRequest(BaseModel):
    """Request model for creating a tenant."""
    id: str = Field(pattern=r'^[a-z0-9-]+$', description="Tenant ID (lowercase alphanumeric with hyphens)")
    name: str = Field(min_length=1, max_length=255, description="Tenant display name")
    config: Optional[Dict[str, Any]] = Field(default=None, description="Tenant configuration")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class TenantUpdateRequest(BaseModel):
    """Request model for updating a tenant."""
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    config: Optional[Dict[str, Any]] = None
    status: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class TenantResponse(BaseModel):
    """Response model for tenant data."""
    id: str
    name: str
    config: Dict[str, Any]
    status: str
    created_at: str
    updated_at: Optional[str] = None
    metadata: Dict[str, Any]


class TenantListResponse(BaseModel):
    """Response model for tenant list."""
    tenants: list
    total: int
    limit: int
    offset: int


@app.post("/api/v1/admin/tenants", response_model=TenantResponse, tags=["Tenants"], status_code=status.HTTP_201_CREATED)
async def create_tenant(
    request: TenantCreateRequest,
    system: PerceptixSystem = Depends(get_system),
    current_user: TokenData = Depends(require_admin),
):
    """
    Create a new tenant.

    **Admin Operation**

    Creates a new tenant with the specified configuration.
    Each tenant gets isolated data storage and configuration.
    """
    try:
        from tenancy.models.tenant import TenantConfig
        from tenancy.models.tenant import TenantCreate

        tenant_manager = _get_tenant_manager()

        # Parse config if provided
        tenant_config = None
        if request.config:
            tenant_config = TenantConfig(**request.config)

        # Create tenant
        tenant_create = TenantCreate(
            id=request.id,
            name=request.name,
            config=tenant_config,
            metadata=request.metadata
        )

        tenant = tenant_manager.create_tenant(tenant_create)

        logger.info(f"Created tenant: {tenant.id}")
        system.historian.record_audit_event(
            actor=current_user.username or "unknown",
            action="tenant.create",
            entity_type="tenant",
            entity_id=tenant.id,
            details={"name": tenant.name},
        )

        return TenantResponse(
            id=tenant.id,
            name=tenant.name,
            config=tenant.config.model_dump(),
            status=tenant.status.value,
            created_at=tenant.created_at.isoformat(),
            updated_at=tenant.updated_at.isoformat() if tenant.updated_at else None,
            metadata=tenant.metadata
        )

    except Exception as e:
        logger.error(f"Failed to create tenant: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create tenant: {str(e)}"
        )


@app.get("/api/v1/admin/tenants", response_model=TenantListResponse, tags=["Tenants"])
async def list_tenants(
    status_filter: Optional[str] = Query(default=None, description="Filter by tenant status"),
    limit: int = Query(default=100, ge=1, le=1000, description="Maximum results"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
    current_user: TokenData = Depends(require_admin),
):
    """
    List all tenants.

    **Admin Operation**

    Returns a paginated list of all tenants in the system.
    Optionally filter by status (active, suspended, inactive).
    """
    try:
        from tenancy import TenantStatus

        tenant_manager = _get_tenant_manager()

        # Parse status filter
        status_obj = None
        if status_filter:
            status_obj = TenantStatus(status_filter)

        # Get tenants
        tenants = tenant_manager.list_tenants(status=status_obj, limit=limit, offset=offset)
        total = tenant_manager.get_tenant_count(status=status_obj)

        # Convert to response format
        tenant_list = [
            {
                'id': t.id,
                'name': t.name,
                'status': t.status.value,
                'created_at': t.created_at.isoformat(),
                'updated_at': t.updated_at.isoformat() if t.updated_at else None
            }
            for t in tenants
        ]

        return TenantListResponse(
            tenants=tenant_list,
            total=total,
            limit=limit,
            offset=offset
        )

    except Exception as e:
        logger.error(f"Failed to list tenants: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list tenants: {str(e)}"
        )


@app.get("/api/v1/admin/tenants/{tenant_id}", response_model=TenantResponse, tags=["Tenants"])
async def get_tenant(
    tenant_id: str,
    current_user: TokenData = Depends(require_admin),
):
    """
    Get tenant details by ID.

    **Admin Operation**

    Returns detailed information about a specific tenant.
    """
    try:
        tenant_manager = _get_tenant_manager()

        # Get tenant
        tenant = tenant_manager.get_tenant(tenant_id)

        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tenant not found: {tenant_id}"
            )

        return TenantResponse(
            id=tenant.id,
            name=tenant.name,
            config=tenant.config.model_dump(),
            status=tenant.status.value,
            created_at=tenant.created_at.isoformat(),
            updated_at=tenant.updated_at.isoformat() if tenant.updated_at else None,
            metadata=tenant.metadata
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get tenant: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get tenant: {str(e)}"
        )


@app.put("/api/v1/admin/tenants/{tenant_id}", response_model=TenantResponse, tags=["Tenants"])
async def update_tenant(
    tenant_id: str,
    request: TenantUpdateRequest,
    system: PerceptixSystem = Depends(get_system),
    current_user: TokenData = Depends(require_admin),
):
    """
    Update tenant configuration.

    **Admin Operation**

    Updates tenant settings including name, configuration, status, and metadata.
    """
    try:
        from tenancy.models.tenant import TenantConfig
        from tenancy import TenantStatus
        from tenancy.models.tenant import TenantUpdate

        tenant_manager = _get_tenant_manager()

        # Parse updates
        tenant_config = None
        if request.config:
            tenant_config = TenantConfig(**request.config)

        status_obj = None
        if request.status:
            status_obj = TenantStatus(request.status)

        # Create update request
        tenant_update = TenantUpdate(
            name=request.name,
            config=tenant_config,
            status=status_obj,
            metadata=request.metadata
        )

        # Update tenant
        tenant = tenant_manager.update_tenant(tenant_id, tenant_update)

        logger.info(f"Updated tenant: {tenant_id}")
        system.historian.record_audit_event(
            actor=current_user.username or "unknown",
            action="tenant.update",
            entity_type="tenant",
            entity_id=tenant_id,
            details={
                "name": tenant.name,
                "status": tenant.status.value,
            },
        )

        return TenantResponse(
            id=tenant.id,
            name=tenant.name,
            config=tenant.config.model_dump(),
            status=tenant.status.value,
            created_at=tenant.created_at.isoformat(),
            updated_at=tenant.updated_at.isoformat() if tenant.updated_at else None,
            metadata=tenant.metadata
        )

    except Exception as e:
        logger.error(f"Failed to update tenant: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to update tenant: {str(e)}"
        )


@app.delete("/api/v1/admin/tenants/{tenant_id}", tags=["Tenants"], status_code=status.HTTP_204_NO_CONTENT)
async def delete_tenant(
    tenant_id: str,
    hard_delete: bool = Query(default=False, description="Permanently delete tenant (default: soft delete)"),
    system: PerceptixSystem = Depends(get_system),
    current_user: TokenData = Depends(require_admin),
):
    """
    Delete a tenant.

    **Admin Operation**

    By default, performs soft delete (marks tenant as inactive).
    Use hard_delete=true to permanently remove tenant and all data.
    """
    try:
        tenant_manager = _get_tenant_manager()

        # Delete tenant
        tenant_manager.delete_tenant(tenant_id, hard_delete=hard_delete)

        logger.warning(f"{'Hard' if hard_delete else 'Soft'} deleted tenant: {tenant_id}")
        system.historian.record_audit_event(
            actor=current_user.username or "unknown",
            action="tenant.delete",
            entity_type="tenant",
            entity_id=tenant_id,
            details={"hard_delete": bool(hard_delete)},
        )

        return None

    except Exception as e:
        logger.error(f"Failed to delete tenant: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to delete tenant: {str(e)}"
        )


# -------------------------------------------------------------------------
# RULES ENGINE ENDPOINTS
# -------------------------------------------------------------------------

# -------------------------------------------------------------------------
# Policy Automation Endpoints (Approval-Gated Remediation Routing)
# -------------------------------------------------------------------------

class PolicyUpsertRequest(BaseModel):
    id: Optional[str] = Field(default=None, description="Policy ID (UUID). If omitted, one is generated.")
    name: str = Field(min_length=3, max_length=200)
    enabled: bool = Field(default=True)
    match: Dict[str, Any] = Field(default_factory=dict, description="Match conditions (incident_types, min_confidence, contains_any, etc.)")
    action: Dict[str, Any] = Field(default_factory=dict, description="Action payload (playbook, require_approval)")


@app.get("/api/v1/admin/policies", tags=["Admin"])
async def list_policies(
    enabled_only: bool = Query(default=False, description="Only return enabled policies"),
    system: PerceptixSystem = Depends(get_system),
    current_user: TokenData = Depends(require_admin),
):
    try:
        policies = system.historian.list_policies(enabled_only=enabled_only)
        return {"policies": policies, "count": len(policies)}
    except Exception as e:
        logger.error(f"Failed to list policies: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.post("/api/v1/admin/policies", tags=["Admin"])
async def upsert_policy(
    request: PolicyUpsertRequest,
    system: PerceptixSystem = Depends(get_system),
    current_user: TokenData = Depends(require_admin),
):
    try:
        import uuid

        policy_id = request.id or str(uuid.uuid4())
        system.historian.upsert_policy(
            policy_id=policy_id,
            name=request.name,
            enabled=bool(request.enabled),
            match=request.match or {},
            action=request.action or {},
        )
        system.historian.record_audit_event(
            actor=current_user.username or "unknown",
            action="policy.upsert",
            entity_type="policy",
            entity_id=policy_id,
            details={"name": request.name, "enabled": bool(request.enabled)},
        )
        return {"success": True, "id": policy_id}
    except Exception as e:
        logger.error(f"Failed to upsert policy: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.delete("/api/v1/admin/policies/{policy_id}", tags=["Admin"])
async def delete_policy(
    policy_id: str,
    system: PerceptixSystem = Depends(get_system),
    current_user: TokenData = Depends(require_admin),
):
    try:
        deleted = system.historian.delete_policy(policy_id)
        if deleted:
            system.historian.record_audit_event(
                actor=current_user.username or "unknown",
                action="policy.delete",
                entity_type="policy",
                entity_id=policy_id,
                details={},
            )
        return {"success": bool(deleted)}
    except Exception as e:
        logger.error(f"Failed to delete policy: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# -------------------------------------------------------------------------
# Webhook Ingestion Endpoints (Orchestration / Observability)
# -------------------------------------------------------------------------

class PipelineEventIngestRequest(BaseModel):
    source: str = Field(min_length=2, max_length=50, description="Origin system: airflow, dbt, dagster, etc.")
    pipeline: str = Field(min_length=2, max_length=200)
    run_id: Optional[str] = Field(default=None, max_length=200)
    status: str = Field(min_length=2, max_length=50, description="RUNNING|SUCCESS|FAILED|ERROR|... (freeform)")
    severity: str = Field(min_length=2, max_length=20, description="LOW|MEDIUM|HIGH|CRITICAL (freeform)")
    message: Optional[str] = Field(default=None, max_length=2000)
    metrics: Dict[str, Any] = Field(default_factory=dict)
    timestamp: Optional[str] = Field(default=None, description="Event timestamp (ISO). Defaults to server time.")


@app.post("/api/v1/ingest/events", tags=["Ingestion"])
async def ingest_pipeline_event(
    request: PipelineEventIngestRequest,
    system: PerceptixSystem = Depends(get_system),
    current_user: TokenData = Depends(get_current_user),
):
    """
    Ingest an orchestration/observability event for the current tenant.
    These events are persisted and become part of the next reasoning context.
    """
    try:
        import uuid

        event_id = str(uuid.uuid4())
        ts = request.timestamp or datetime.now().isoformat()
        system.historian.record_pipeline_event(
            event_id=event_id,
            tenant_id=getattr(system, "tenant_id", None),
            source=request.source,
            pipeline=request.pipeline,
            run_id=request.run_id,
            status=request.status,
            severity=request.severity,
            message=request.message,
            metrics=request.metrics,
            event_timestamp=ts,
        )

        await broadcast_to_websockets(
            {
                "type": "pipeline_event",
                "data": {
                    "id": event_id,
                    "source": request.source,
                    "pipeline": request.pipeline,
                    "run_id": request.run_id,
                    "status": request.status,
                    "severity": request.severity,
                    "message": request.message,
                    "timestamp": ts,
                },
                "timestamp": datetime.now().isoformat(),
            },
            tenant_id=getattr(system, "tenant_id", None),
        )

        return {"success": True, "id": event_id}
    except Exception as e:
        logger.error(f"Failed to ingest pipeline event: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# -------------------------------------------------------------------------
# Structured Ingestion Endpoints (Airflow / Datadog / Alertmanager)
# -------------------------------------------------------------------------

class AirflowDagRunIngestRequest(BaseModel):
    dag_id: str = Field(min_length=1, max_length=250)
    run_id: str = Field(min_length=1, max_length=250)
    state: str = Field(min_length=1, max_length=50, description="success|failed|running|queued|... (freeform)")
    logical_date: Optional[str] = Field(default=None, description="ISO timestamp")
    start_date: Optional[str] = Field(default=None, description="ISO timestamp")
    end_date: Optional[str] = Field(default=None, description="ISO timestamp")
    external_url: Optional[str] = Field(default=None, max_length=1000)
    message: Optional[str] = Field(default=None, max_length=2000)


@app.post("/api/v1/ingest/airflow/dag-run", tags=["Ingestion"])
async def ingest_airflow_dag_run(
    request: AirflowDagRunIngestRequest,
    system: PerceptixSystem = Depends(get_system),
    current_user: TokenData = Depends(get_current_user),
):
    """
    Ingest a single Airflow DAG run status update.

    This is a convenience wrapper around /api/v1/ingest/events that preserves Airflow fields
    and maps them into Perceptix pipeline events.
    """
    try:
        import uuid

        state = (request.state or "").strip().upper()
        severity = "LOW"
        if state in {"FAILED", "ERROR"}:
            severity = "HIGH"
        elif state in {"UP_FOR_RETRY"}:
            severity = "MEDIUM"

        event_id = str(uuid.uuid4())
        ts = request.logical_date or request.end_date or request.start_date or datetime.now().isoformat()
        system.historian.record_pipeline_event(
            event_id=event_id,
            tenant_id=getattr(system, "tenant_id", None),
            source="airflow",
            pipeline=request.dag_id,
            run_id=request.run_id,
            status=state or request.state,
            severity=severity,
            message=request.message or f"Airflow DAG run {request.run_id} is {request.state}",
            metrics={
                "logical_date": request.logical_date,
                "start_date": request.start_date,
                "end_date": request.end_date,
                "external_url": request.external_url,
            },
            event_timestamp=ts,
        )

        await broadcast_to_websockets(
            {
                "type": "pipeline_event",
                "data": {
                    "id": event_id,
                    "source": "airflow",
                    "pipeline": request.dag_id,
                    "run_id": request.run_id,
                    "status": request.state,
                    "severity": severity,
                    "message": request.message,
                    "timestamp": ts,
                },
                "timestamp": datetime.now().isoformat(),
            },
            tenant_id=getattr(system, "tenant_id", None),
        )

        return {"success": True, "id": event_id}
    except Exception as e:
        logger.error(f"Failed to ingest Airflow dag run: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


class DatadogEventIngestRequest(BaseModel):
    title: Optional[str] = Field(default=None, max_length=500)
    text: Optional[str] = Field(default=None, max_length=4000)
    alert_type: Optional[str] = Field(default=None, max_length=50, description="info|warning|error|success")
    event_type: Optional[str] = Field(default=None, max_length=100)
    tags: Optional[list[str]] = Field(default=None)
    date_happened: Optional[int] = Field(default=None, description="Unix timestamp (seconds)")
    aggregation_key: Optional[str] = Field(default=None, max_length=200)


@app.post("/api/v1/ingest/datadog/event", tags=["Ingestion"])
async def ingest_datadog_event(
    request: DatadogEventIngestRequest,
    system: PerceptixSystem = Depends(get_system),
    current_user: TokenData = Depends(get_current_user),
):
    """
    Ingest a Datadog event/monitor webhook payload.
    """
    try:
        import uuid
        from datetime import datetime, timezone

        alert_type = (request.alert_type or "").strip().lower()
        severity = "LOW"
        if alert_type in {"error"}:
            severity = "HIGH"
        elif alert_type in {"warning"}:
            severity = "MEDIUM"

        event_id = str(uuid.uuid4())
        ts = datetime.now(timezone.utc).isoformat()
        if request.date_happened:
            ts = datetime.fromtimestamp(int(request.date_happened), tz=timezone.utc).isoformat()

        title = request.title or "Datadog event"
        message = request.text or title

        system.historian.record_pipeline_event(
            event_id=event_id,
            tenant_id=getattr(system, "tenant_id", None),
            source="datadog",
            pipeline=request.aggregation_key or request.event_type or "datadog",
            run_id=None,
            status=alert_type or "event",
            severity=severity,
            message=message,
            metrics={
                "title": title,
                "tags": request.tags or [],
                "event_type": request.event_type,
            },
            event_timestamp=ts,
        )

        await broadcast_to_websockets(
            {
                "type": "pipeline_event",
                "data": {
                    "id": event_id,
                    "source": "datadog",
                    "pipeline": request.aggregation_key or request.event_type or "datadog",
                    "run_id": None,
                    "status": alert_type or "event",
                    "severity": severity,
                    "message": title,
                    "timestamp": ts,
                },
                "timestamp": datetime.now().isoformat(),
            },
            tenant_id=getattr(system, "tenant_id", None),
        )

        return {"success": True, "id": event_id}
    except Exception as e:
        logger.error(f"Failed to ingest Datadog event: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


class AlertmanagerWebhookRequest(BaseModel):
    status: Optional[str] = None
    receiver: Optional[str] = None
    alerts: list[Dict[str, Any]] = Field(default_factory=list)
    groupLabels: Optional[Dict[str, Any]] = None
    commonLabels: Optional[Dict[str, Any]] = None
    commonAnnotations: Optional[Dict[str, Any]] = None
    externalURL: Optional[str] = None


@app.post("/api/v1/ingest/alertmanager", tags=["Ingestion"])
async def ingest_alertmanager_webhook(
    request: AlertmanagerWebhookRequest,
    system: PerceptixSystem = Depends(get_system),
    current_user: TokenData = Depends(get_current_user),
):
    """
    Ingest a Prometheus Alertmanager webhook.
    """
    try:
        import uuid

        created_ids: list[str] = []
        for alert in request.alerts or []:
            labels = alert.get("labels") or {}
            annotations = alert.get("annotations") or {}
            alert_name = labels.get("alertname") or labels.get("alert") or "alert"
            status = (alert.get("status") or request.status or "firing").upper()

            severity_label = (labels.get("severity") or "").lower()
            severity = "LOW"
            if severity_label in {"critical", "high"}:
                severity = "CRITICAL"
            elif severity_label in {"warning", "medium"}:
                severity = "MEDIUM"

            event_id = str(uuid.uuid4())
            ts = alert.get("startsAt") or datetime.now().isoformat()
            message = annotations.get("summary") or annotations.get("description") or f"{alert_name} is {status}"

            system.historian.record_pipeline_event(
                event_id=event_id,
                tenant_id=getattr(system, "tenant_id", None),
                source="alertmanager",
                pipeline=str(alert_name),
                run_id=None,
                status=status,
                severity=severity,
                message=message,
                metrics={
                    "labels": labels,
                    "annotations": annotations,
                    "endsAt": alert.get("endsAt"),
                    "externalURL": request.externalURL,
                },
                event_timestamp=ts,
            )
            created_ids.append(event_id)

        if created_ids:
            await broadcast_to_websockets(
                {
                    "type": "pipeline_event_batch",
                    "data": {"count": len(created_ids), "ids": created_ids, "source": "alertmanager"},
                    "timestamp": datetime.now().isoformat(),
                },
                tenant_id=getattr(system, "tenant_id", None),
            )

        return {"success": True, "count": len(created_ids), "ids": created_ids}
    except Exception as e:
        logger.error(f"Failed to ingest Alertmanager webhook: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

class RuleResponse(BaseModel):
    """Response model for rule data."""
    id: str
    name: str
    description: str
    enabled: bool
    priority: str
    conditions: Dict[str, Any]
    actions: list
    cooldown_minutes: int
    max_triggers_per_day: int
    tags: list
    metadata: Dict[str, Any]


class RuleListResponse(BaseModel):
    """Response model for listing rules."""
    total: int
    rules: list


class RuleStatsResponse(BaseModel):
    """Response model for rule statistics."""
    rule_id: str
    enabled: bool
    priority: str
    total_triggers: int
    today_triggers: int
    last_triggered: Optional[str]
    cooldown_remaining_seconds: int


class RuleTestRequest(BaseModel):
    """Request model for testing a rule."""
    context: Dict[str, Any]


class RuleTestResponse(BaseModel):
    """Response model for rule test results."""
    rule_id: str
    matched: bool
    conditions_met: Dict[str, bool]
    evaluation_time: str
    error: Optional[str]


@app.get("/api/v1/rules", response_model=RuleListResponse, tags=["Rules"])
async def list_rules(
    enabled_only: bool = Query(False, description="Only return enabled rules"),
    tags: Optional[str] = Query(None, description="Filter by tags (comma-separated)"),
    system: PerceptixSystem = Depends(get_system)
):
    """
    List all custom alerting rules.

    **Query Parameters:**
    - enabled_only: Only return enabled rules
    - tags: Filter rules by tags
    """
    try:
        if not system.observer.rules_engine:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Rules engine not enabled"
            )

        rules_engine = system.observer.rules_engine

        # Parse tags if provided
        tag_list = tags.split(",") if tags else None

        # Get rules
        rules = rules_engine.list_rules(enabled_only=enabled_only, tags=tag_list)

        return RuleListResponse(
            total=len(rules),
            rules=[rule.to_dict() for rule in rules]
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list rules: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list rules: {str(e)}"
        )


@app.get("/api/v1/rules/{rule_id}", response_model=RuleResponse, tags=["Rules"])
async def get_rule(rule_id: str, system: PerceptixSystem = Depends(get_system)):
    """
    Get a specific rule by ID.
    """
    try:
        if not system.observer.rules_engine:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Rules engine not enabled"
            )

        rules_engine = system.observer.rules_engine
        rule = rules_engine.get_rule(rule_id)

        if not rule:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Rule not found: {rule_id}"
            )

        return RuleResponse(**rule.to_dict())

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get rule: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get rule: {str(e)}"
        )


@app.get("/api/v1/rules/{rule_id}/stats", response_model=RuleStatsResponse, tags=["Rules"])
async def get_rule_stats(rule_id: str, system: PerceptixSystem = Depends(get_system)):
    """
    Get statistics for a specific rule.

    Returns:
    - Total triggers
    - Today's triggers
    - Last trigger time
    - Cooldown remaining
    """
    try:
        if not system.observer.rules_engine:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Rules engine not enabled"
            )

        rules_engine = system.observer.rules_engine
        stats = rules_engine.get_rule_stats(rule_id)

        return RuleStatsResponse(**stats)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to get rule stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get rule stats: {str(e)}"
        )


@app.post("/api/v1/rules/{rule_id}/test", response_model=RuleTestResponse, tags=["Rules"])
async def test_rule(
    rule_id: str, 
    request: RuleTestRequest,
    system: PerceptixSystem = Depends(get_system)
):
    """
    Test a rule against a provided context without executing actions.

    Useful for validating rules before enabling them.
    """
    try:
        if not system.observer.rules_engine:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Rules engine not enabled"
            )

        rules_engine = system.observer.rules_engine
        result = rules_engine.test_rule(rule_id, request.context)

        return RuleTestResponse(
            rule_id=result.rule_id,
            matched=result.matched,
            conditions_met=result.conditions_met,
            evaluation_time=result.evaluation_time.isoformat(),
            error=result.error
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to test rule: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to test rule: {str(e)}"
        )


@app.post("/api/v1/rules/{rule_id}/enable", tags=["Rules"])
async def enable_rule(rule_id: str, system: PerceptixSystem = Depends(get_system)):
    """
    Enable a rule.
    """
    try:
        if not system.observer.rules_engine:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Rules engine not enabled"
            )

        rules_engine = system.observer.rules_engine
        rule = rules_engine.get_rule(rule_id)

        if not rule:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Rule not found: {rule_id}"
            )

        rule.enabled = True
        rules_engine.update_rule(rule)

        logger.info(f"Enabled rule: {rule_id}")

        return {"message": f"Rule {rule_id} enabled", "success": True}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to enable rule: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to enable rule: {str(e)}"
        )


@app.post("/api/v1/rules/{rule_id}/disable", tags=["Rules"])
async def disable_rule(rule_id: str, system: PerceptixSystem = Depends(get_system)):
    """
    Disable a rule.
    """
    try:
        if not system.observer.rules_engine:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Rules engine not enabled"
            )

        rules_engine = system.observer.rules_engine
        rule = rules_engine.get_rule(rule_id)

        if not rule:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Rule not found: {rule_id}"
            )

        rule.enabled = False
        rules_engine.update_rule(rule)

        logger.info(f"Disabled rule: {rule_id}")

        return {"message": f"Rule {rule_id} disabled", "success": True}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to disable rule: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to disable rule: {str(e)}"
        )


@app.post("/api/v1/rules/reload", tags=["Rules"])
async def reload_rules(system: PerceptixSystem = Depends(get_system)):
    """
    Reload all rules from disk.

    Useful when rules are updated externally.
    """
    try:
        if not system.observer.rules_engine:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Rules engine not enabled"
            )

        rules_engine = system.observer.rules_engine
        rules_engine.reload_rules()

        logger.info("Reloaded all rules from disk")

        return {
            "message": "Rules reloaded successfully",
            "total_rules": len(rules_engine.rules),
            "success": True
        }

    except Exception as e:
        logger.error(f"Failed to reload rules: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reload rules: {str(e)}"
        )


@app.get("/api/v1/rules/summary", tags=["Rules"])
async def get_rules_summary(system: PerceptixSystem = Depends(get_system)):
    """
    Get summary of rules engine status.

    Returns:
    - Total rules
    - Enabled/disabled counts
    - Priority distribution
    """
    try:
        if not system.observer.rules_engine:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Rules engine not enabled"
            )

        rules_engine = system.observer.rules_engine
        summary = rules_engine.get_summary()

        return summary

    except Exception as e:
        logger.error(f"Failed to get rules summary: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get rules summary: {str(e)}"
        )


# -------------------------------------------------------------------------
# Meta-Learning Endpoints
# -------------------------------------------------------------------------

@app.get("/api/v1/meta/analysis", response_model=MetaAnalysisResponse, tags=["Meta-Learning"])
async def get_meta_analysis(system: PerceptixSystem = Depends(get_system)):
    """
    Run and retrieve a meta-analysis of historical incidents.
    Detects recurring patterns and provides systemic recommendations.
    """
    try:
        analysis = system.meta_learner.analyze_patterns()
        return MetaAnalysisResponse(
            period_analyzed=analysis.period_analyzed,
            total_incidents=analysis.total_incidents,
            most_frequent_type=analysis.most_frequent_type,
            detected_pattern=analysis.detected_pattern.model_dump(),
            recommendation=analysis.recommendation
        )
    except Exception as e:
        logger.error(f"Meta-analysis failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Meta-analysis failed: {str(e)}"
        )


# -------------------------------------------------------------------------
# Remediation Endpoints
# -------------------------------------------------------------------------

@app.get("/api/v1/remediation/playbooks", response_model=list[PlaybookResponse], tags=["Remediation"])
async def list_playbooks(system: PerceptixSystem = Depends(get_system)):
    """List all available remediation playbooks."""
    return system.remediation_engine.list_playbooks()


@app.get("/api/v1/remediation/approvals", response_model=list[RemediationApprovalResponse], tags=["Remediation"])
async def list_pending_approvals(system: PerceptixSystem = Depends(get_system)):
    """List all pending remediation actions requiring human approval."""
    return system.remediation_engine.get_pending_approvals()


class ApprovalRequest(BaseModel):
    token_id: str
    approver: str
    comment: Optional[str] = None

@app.post("/api/v1/remediation/approve", tags=["Remediation"])
async def approve_remediation(
    request: ApprovalRequest,
    system: PerceptixSystem = Depends(get_system),
    current_user: TokenData = Depends(get_current_user)
):
    """Approve a pending remediation action."""
    # Use system instance instead of app_state
    success = system.remediation_engine.approve_remediation(
        request.token_id, request.approver, request.comment
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Approval failed or token expired"
        )
        
    return {"message": "Remediation approved and queued for execution", "success": True}


class RejectionRequest(BaseModel):
    token_id: str
    rejector: str
    reason: Optional[str] = None

@app.post("/api/v1/remediation/reject", tags=["Remediation"])
async def reject_remediation(
    request: RejectionRequest,
    system: PerceptixSystem = Depends(get_system),
    current_user: TokenData = Depends(get_current_user)
):
    """Reject a pending remediation action."""
    # Use system instance instead of app_state
    success = system.remediation_engine.reject_remediation(
        request.token_id, request.rejector, request.reason
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Rejection failed or token expired"
        )
        
    return {"message": "Remediation rejected", "success": True}


class ConfigUpdateRequest(BaseModel):
    key: str
    value: str

@app.post("/api/v1/admin/config", tags=["Admin"])
async def update_config(
    request: ConfigUpdateRequest,
    system: PerceptixSystem = Depends(get_system),
    current_user: TokenData = Depends(require_admin)
):
    """
    Update a dynamic configuration setting.
    """
    try:
        # Update in DB
        system.db_manager.set_app_config(request.key, request.value)
        
        # Apply to current instance
        from config import apply_dynamic_settings
        apply_dynamic_settings(system.config, {request.key: request.value})

        system.historian.record_audit_event(
            actor=current_user.username or "unknown",
            action="config.update",
            entity_type="config",
            entity_id=request.key,
            details={"value": request.value},
        )
        logger.info(f"Configuration updated: {request.key}={request.value}")
        return {"success": True, "message": f"Updated {request.key}"}
        
    except Exception as e:
        logger.error(f"Config update failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update config: {str(e)}"
        )


@app.post("/api/v1/admin/reset-demo-data", tags=["Admin"])
async def reset_demo_data(
    system: PerceptixSystem = Depends(get_system),
    current_user: TokenData = Depends(require_admin)
):
    """
    Reset demo dashboard data (incidents + metrics) and in-memory counters.

    Intended for recording retakes and demo environment cleanup.
    """
    try:
        deleted = system.historian.reset_demo_data()

        # Reset in-memory runtime counters so KPI cards start from zero again.
        system.metrics.collector.reset()
        system.cycle_count = 0
        system.last_cycle_timestamp = None

        logger.warning(
            "Demo data reset requested by %s (incidents=%d, metrics=%d)",
            current_user.username,
            deleted.get("incidents_deleted", 0),
            deleted.get("metrics_deleted", 0),
        )

        system.historian.record_audit_event(
            actor=current_user.username or "unknown",
            action="demo.reset",
            entity_type="system",
            entity_id="demo_data",
            details=deleted,
        )
        return {
            "success": True,
            "message": "Demo data reset successfully",
            **deleted,
        }
    except Exception as e:
        logger.error(f"Demo data reset failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reset demo data: {str(e)}"
        )


# -------------------------------------------------------------------------
# TERMINAL EXECUTION BLOCK
# -------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    print("\n" + "="*70)
    print("PERCEPTIX REST API - STARTING SERVER")
    print("="*70 + "\n")

    print("Server will be available at:")
    print(f"  - API Documentation: http://localhost:{_initial_config.api.port}/docs")
    print(f"  - Alternative Docs: http://localhost:{_initial_config.api.port}/redoc")
    print(f"  - Health Check: http://localhost:{_initial_config.api.port}/health")
    print(f"  - Prometheus Metrics: http://localhost:{_initial_config.api.port}/metrics")
    print("\nPress Ctrl+C to stop the server\n")

    uvicorn.run(
        "api:app",
        host=_initial_config.api.host,
        port=_initial_config.api.port,
        log_level=_initial_config.system.log_level.lower(),
        reload=False
    )
