"""
Observer Module: System State Monitoring with Validation.
Collects signals, metrics, and context for the Reasoner.
"""
import json
import logging
import os
import time
import uuid
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pydantic import ValidationError as PydanticValidationError

from config import PerceptixConfig
from datasource import SQLiteDataSource, WarehouseDataSource
from exceptions import DataFetchError, InvalidSystemStateError, ObserverError
from models import (
    ObservationPackage,
    SystemState,
    TableMetric,
    Telemetry,
    SystemMetadata,
    HistoricalBaseline,
)


logger = logging.getLogger("PerceptixObserver")


class Observer:
    """
    The Sensory System of Project Perceptix.
    Fetches raw signals from DataSource and packages validated state for the Reasoner.
    """

    def __init__(self, config: PerceptixConfig):
        self.config = config
        self.component_id = "OBSERVER_V2"
        self.version = config.system.version

        # Initialize data source.
        try:
            ds_type = (config.observer.data_source_type or "sqlite").lower()
            if ds_type == "sqlite":
                self.datasource = SQLiteDataSource(config.observer.data_source_path)
            elif ds_type in ("bigquery", "snowflake"):
                connector_cfg = dict(config.observer.warehouse_config or {})
                if ds_type == "bigquery":
                    connector_cfg.setdefault("project_id", os.getenv("BIGQUERY_PROJECT_ID"))
                    connector_cfg.setdefault("credentials_path", os.getenv("BIGQUERY_CREDENTIALS_PATH"))
                    if not connector_cfg.get("project_id"):
                        raise ValueError("Missing BigQuery config: BIGQUERY_PROJECT_ID (or observer.warehouse_config.project_id)")
                else:
                    connector_cfg.setdefault("account", os.getenv("SNOWFLAKE_ACCOUNT"))
                    connector_cfg.setdefault("user", os.getenv("SNOWFLAKE_USER"))
                    connector_cfg.setdefault("password", os.getenv("SNOWFLAKE_PASSWORD"))
                    connector_cfg.setdefault("warehouse", os.getenv("SNOWFLAKE_WAREHOUSE"))
                    connector_cfg.setdefault("database", os.getenv("SNOWFLAKE_DATABASE"))
                    connector_cfg.setdefault("schema", os.getenv("SNOWFLAKE_SCHEMA", "PUBLIC"))
                    connector_cfg.setdefault("role", os.getenv("SNOWFLAKE_ROLE", "SYSADMIN"))
                    missing = [k for k in ("account", "user", "password", "warehouse", "database") if not connector_cfg.get(k)]
                    if missing:
                        raise ValueError(f"Missing Snowflake config fields: {', '.join(missing)}")

                monitored_tables = list(config.observer.monitored_tables or [])
                if not monitored_tables:
                    raise ValueError("No monitored tables configured (PERCEPTIX_MONITORED_TABLES or observer.monitored_tables)")

                self.datasource = WarehouseDataSource(
                    connector_type=ds_type,
                    connector_config=connector_cfg,
                    monitored_tables=monitored_tables,
                    table_timestamp_columns=dict(config.observer.table_timestamp_columns or {}),
                    table_null_columns=dict(config.observer.table_null_columns or {}),
                )
                logger.info("Warehouse data source initialized: %s (%d tables)", ds_type, len(monitored_tables))
            else:
                raise ValueError(f"Unsupported data source type: {ds_type}")
        except Exception as e:
            raise ObserverError(
                f"Failed to initialize data source: {e}",
                component=self.component_id,
            )

        # Initialize ML detector if enabled.
        self.ml_detector: Optional[Any] = None
        if config.ml.enabled:
            try:
                from ml.ml_anomaly_detector import MLAnomalyDetector

                self.ml_detector = MLAnomalyDetector(
                    models_dir=config.ml.models_dir,
                    enable_isolation_forest=config.ml.enable_isolation_forest,
                    enable_autoencoder=config.ml.enable_autoencoder,
                    enable_forecaster=config.ml.enable_forecaster,
                    ensemble_threshold=config.ml.ensemble_threshold,
                )
                logger.info("ML Anomaly Detection enabled and initialized")
            except ImportError:
                logger.warning("ML modules not available, ML detection disabled")
            except Exception as e:
                logger.error("Failed to initialize ML detector: %s", e)

        # Initialize custom rules engine if enabled.
        self.rules_engine: Optional[Any] = None
        if config.rules_engine.enabled:
            try:
                from rules_engine import RulesEngine

                self.rules_engine = RulesEngine(
                    rules_path=config.rules_engine.rules_path,
                    cooldown_db_path=config.rules_engine.cooldown_db_path,
                    logger=logger,
                )
                logger.info(
                    "Rules Engine enabled with %d rules loaded",
                    len(self.rules_engine.rules),
                )
            except ImportError:
                logger.warning("Rules engine modules not available, rules engine disabled")
            except Exception as e:
                logger.error("Failed to initialize rules engine: %s", e)

        self._log_event(
            "system_startup",
            {
                "status": "initialized",
                "version": self.version,
                "data_source": config.observer.data_source_type,
                "ml_enabled": self.ml_detector is not None,
                "rules_engine_enabled": self.rules_engine is not None,
            },
        )

    def _log_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Emit a structured JSON log entry."""
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "component": self.component_id,
            "event_type": event_type,
            "payload": payload,
        }
        logger.debug(json.dumps(log_entry))

    def _generate_telemetry(self, start_time: float) -> Telemetry:
        """Calculate latency and generate trace IDs."""
        latency_ms = (time.time() - start_time) * 1000
        return Telemetry(
            trace_id=str(uuid.uuid4()),
            latency_ms=round(latency_ms, 2),
            component=self.component_id,
            version=self.version,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    async def _fetch_raw_data(self) -> Dict[str, Any]:
        """Fetch raw data from the configured DataSource."""
        try:
            # Use configured list of monitored tables; keep stable keys for the rest of the pipeline.
            tables = list(self.config.observer.monitored_tables or [])
            metrics_by_table: Dict[str, Any] = {}
            for t in tables:
                metrics_by_table[t] = await self.datasource.get_table_metrics(t)

            pipeline_events: list[dict[str, Any]] = []
            try:
                pipeline_events = self._fetch_recent_pipeline_events(limit=20)
            except Exception:
                pipeline_events = []

            current_state = {
                "metadata": {
                    "domain": os.getenv("PERCEPTIX_DOMAIN", "Data Reliability"),
                    "environment": (
                        self.config.system.environment.capitalize()
                        if self.config.system.environment
                        else "Production"
                    ),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                "table_metrics": {
                    f"{name}_table": metrics for name, metrics in metrics_by_table.items()
                },
                "dependency_map": {
                    # Optional dependencies can be injected by configuration in real deployments.
                },
                "historical_baseline_7d": {
                    # Baselines are optional and can be computed by meta-learning.
                },
                "pipeline_events": pipeline_events,
                "recent_code_commits": await self.datasource.get_recent_commits(),
                "alert_history": [],
                "sla_definitions": {
                    # Optional per-consumer SLAs can be attached here.
                },
            }
            return current_state
        except Exception as e:
            raise DataFetchError(
                f"Failed to fetch raw data: {e}",
                component=self.component_id,
            )

    def _fetch_recent_pipeline_events(self, limit: int = 20) -> list[dict[str, Any]]:
        """
        Fetch recent pipeline/orchestration events from the Perceptix DB (if present).

        This is used to enrich the reasoning context with real-world run signals.
        """
        if str(self.config.database.type).lower() != "sqlite":
            return []

        db_path = self.config.database.path
        if not db_path:
            return []

        con = sqlite3.connect(db_path)
        try:
            # Table may not exist for older DBs; fail closed.
            exists = con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='pipeline_events'"
            ).fetchone()
            if not exists:
                return []

            rows = con.execute(
                """
                SELECT id, source, pipeline, run_id, status, severity, message, metrics_json, event_timestamp
                FROM pipeline_events
                ORDER BY event_timestamp DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()

            out: list[dict[str, Any]] = []
            for r in rows:
                try:
                    metrics = json.loads(r[7] or "{}")
                except Exception:
                    metrics = {}
                out.append(
                    {
                        "id": r[0],
                        "source": r[1],
                        "pipeline": r[2],
                        "run_id": r[3],
                        "status": r[4],
                        "severity": r[5],
                        "message": r[6],
                        "metrics": metrics,
                        "timestamp": r[8],
                    }
                )
            return out
        finally:
            con.close()

    def _validate_and_parse_state(self, raw_data: Dict[str, Any]) -> SystemState:
        """Validate and parse raw data into SystemState model."""
        try:
            return SystemState(**raw_data)
        except PydanticValidationError as e:
            errors = e.errors()
            error_details = [f"{err['loc']}: {err['msg']}" for err in errors]
            raise InvalidSystemStateError(
                f"System state validation failed: {'; '.join(error_details)}",
                component=self.component_id,
                context={"validation_errors": errors},
            )
        except Exception as e:
            raise InvalidSystemStateError(
                f"Unexpected error during state validation: {e}",
                component=self.component_id,
            )

    def _run_ml_predictions(self, system_state: SystemState) -> Dict[str, Any]:
        """Run ML anomaly predictions on system metrics."""
        if not self.ml_detector or not self.ml_detector.is_trained:
            return {}

        ml_predictions: Dict[str, Any] = {}
        try:
            for table_name, metric in system_state.table_metrics.items():
                try:
                    table_metric = (
                        metric
                        if isinstance(metric, TableMetric)
                        else TableMetric(**metric.model_dump(), timestamp=datetime.now())
                    )
                    prediction = self.ml_detector.predict(table_metric)
                    ml_predictions[table_name] = {
                        "is_anomaly": prediction.is_anomaly,
                        "anomaly_score": float(prediction.anomaly_score),
                        "confidence": float(prediction.confidence),
                        "model_scores": {
                            k: float(v) for k, v in prediction.model_scores.items()
                        },
                        "timestamp": prediction.timestamp.isoformat(),
                    }
                except Exception:
                    # Do not block the pipeline for one table.
                    continue
        except Exception:
            return {}

        return ml_predictions

    def _evaluate_custom_rules(self, system_state: SystemState) -> Dict[str, Any]:
        """Evaluate custom alerting rules."""
        if not self.rules_engine:
            return {}
        try:
            context = self._build_rules_context(system_state)
            return self.rules_engine.evaluate_and_execute(context)
        except Exception as e:
            logger.error("Rules evaluation failed: %s", e)
            return {}

    def _build_rules_context(self, system_state: SystemState) -> Dict[str, Any]:
        """Build context for rules engine."""
        context: Dict[str, Any] = {
            "metadata": system_state.metadata.model_dump(),
            "dependency_map": system_state.dependency_map,
        }

        for table_name, metrics in system_state.table_metrics.items():
            context[f"{table_name}_row_count"] = metrics.row_count
            context[f"{table_name}_freshness"] = metrics.freshness_minutes
            for col, rate in metrics.null_rates.items():
                context[f"{table_name}_{col}_null_rate"] = rate

        context["rule_table"] = "orders_table"
        context["rule_column"] = "attribution_source"
        context["rule_threshold"] = 0.5
        context["rule_value"] = context.get("orders_table_attribution_source_null_rate", 0.0)
        return context

    async def get_system_state(self, simulate_failure: bool = False) -> ObservationPackage:
        """
        Retrieve the current validated system state package.
        """
        start_time = time.time()
        try:
            if simulate_failure:
                # Demo reliability: do not depend on external connectors.
                # Simulated failures must be fast and deterministic for recording/demo.
                scenario = os.getenv("SIM_SCENARIO", "SCHEMA_CHANGE")
                system_state = self._build_simulated_system_state(scenario=scenario)
            else:
                raw_data = await self._fetch_raw_data()
                system_state = self._validate_and_parse_state(raw_data)

            ml_predictions = self._run_ml_predictions(system_state)
            rules_evaluation = self._evaluate_custom_rules(system_state)
            telemetry = self._generate_telemetry(start_time)

            package = ObservationPackage(
                telemetry=telemetry.model_dump(),
                payload=system_state,
            )

            if ml_predictions:
                package_dict = package.model_dump()
                package_dict["ml_predictions"] = ml_predictions
                package = ObservationPackage(**package_dict)

            if rules_evaluation:
                package_dict = package.model_dump()
                package_dict["rules_evaluation"] = rules_evaluation
                package = ObservationPackage(**package_dict)

            return package
        except Exception as e:
            if hasattr(self, "datasource"):
                try:
                    await self.datasource.disconnect()
                except Exception:
                    pass
            raise ObserverError(f"Unexpected error: {e}", component=self.component_id)

    def _build_simulated_system_state(self, *, scenario: str) -> SystemState:
        """
        Build a minimal, valid SystemState that triggers the agent loop without any external I/O.

        Used only when simulate_failure=True.
        """
        now = datetime.now(timezone.utc).isoformat()
        metadata = SystemMetadata(domain="perceptix-demo", environment="Production", timestamp=now)

        orders = TableMetric(
            row_count=125_000,
            freshness_minutes=5,
            null_rates={"attribution_source": 0.01},
            table_name="orders_table",
            last_updated=now,
        )
        inventory = TableMetric(
            row_count=52_000,
            freshness_minutes=10,
            null_rates={"sku": 0.0},
            table_name="inventory_table",
            last_updated=now,
        )

        baseline_7d = {
            "orders_table": HistoricalBaseline(avg_daily_rows=120_000, avg_attribution_null_rate=0.01),
            "inventory_table": HistoricalBaseline(avg_daily_rows=50_000, avg_attribution_null_rate=0.0),
        }

        pipeline_events: list[dict] = []
        scenario_norm = str(scenario or "").upper()
        if scenario_norm == "INVENTORY":
            inventory.freshness_minutes = 2880
            pipeline_events.append(
                {
                    "source": "airflow",
                    "pipeline": "inventory_sync",
                    "run_id": f"sim-{int(time.time())}",
                    "status": "FAILED",
                    "severity": "HIGH",
                    "message": "Simulated inventory sync failure",
                    "timestamp": now,
                }
            )
            logger.info("Simulating failure: inventory_table freshness=2880 (stale) + failed pipeline event")
        else:
            orders.null_rates["attribution_source"] = 0.99
            pipeline_events.append(
                {
                    "source": "airflow",
                    "pipeline": "daily_orders",
                    "run_id": f"sim-{int(time.time())}",
                    "status": "FAILED",
                    "severity": "HIGH",
                    "message": "Simulated load_orders failure",
                    "timestamp": now,
                }
            )
            logger.info("Simulating failure: orders_table.attribution_source null_rate=0.99 + failed pipeline event")

        return SystemState(
            metadata=metadata,
            table_metrics={
                "orders_table": orders,
                "inventory_table": inventory,
            },
            dependency_map={
                "orders_table": ["inventory_table"],
                "inventory_table": [],
            },
            historical_baseline_7d=baseline_7d,
            pipeline_events=pipeline_events,
            recent_code_commits=[],
            alert_history=[],
            sla_definitions={},
        )
