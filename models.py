"""
Pydantic Models for Data Validation
Defines all data structures used throughout the Cognizant system.
"""
from datetime import datetime
from typing import Dict, List, Optional, Any, Literal
from pydantic import BaseModel, Field, field_validator, ConfigDict
from enum import Enum


# -------------------------------------------------------------------------
# ENUMS
# -------------------------------------------------------------------------

class IncidentType(str, Enum):
    """Types of incidents detected by the system."""
    DATA_INTEGRITY_FAILURE = "DATA_INTEGRITY_FAILURE"
    ROW_COUNT_DROP = "ROW_COUNT_DROP"
    SCHEMA_CHANGE = "SCHEMA_CHANGE"
    API_LATENCY_SPIKE = "API_LATENCY_SPIKE"
    FRESHNESS_VIOLATION = "FRESHNESS_VIOLATION"
    DISTRIBUTION_DRIFT = "DISTRIBUTION_DRIFT"
    UPSTREAM_DELAY = "UPSTREAM_DELAY"
    PII_LEAKAGE = "PII_LEAKAGE"
    SCHEMA_EVOLUTION = "SCHEMA_EVOLUTION"
    UNKNOWN = "UNKNOWN"


class RootCauseCategory(str, Enum):
    """Categories for the root cause of an incident."""
    CODE_CHANGE = "CODE_CHANGE"
    INFRA_FAILURE = "INFRA_FAILURE"
    UPSTREAM_DATA = "UPSTREAM_DATA"
    HUMAN_ERROR = "HUMAN_ERROR"
    UNKNOWN = "UNKNOWN"


class VerificationStatus(str, Enum):
    """Status of hypothesis verification."""
    CONFIRMED = "CONFIRMED"
    WEAK_EVIDENCE = "WEAK_EVIDENCE"
    UNVERIFIED = "UNVERIFIED"
    REJECTED = "REJECTED"


class Criticality(str, Enum):
    """Incident severity levels."""
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class SystemMode(str, Enum):
    """Operating modes for the system."""
    PRODUCTION = "PRODUCTION"
    DEMO = "DEMO"
    MOCK = "MOCK"


# -------------------------------------------------------------------------
# OBSERVER MODELS
# -------------------------------------------------------------------------

class NullRates(BaseModel):
    """Null rate statistics for table columns."""
    model_config = ConfigDict(extra='allow')  # Allow dynamic column names

    @field_validator('*', mode='before')
    @classmethod
    def validate_null_rate(cls, v):
        """Ensure null rates are between 0 and 1."""
        if not isinstance(v, (int, float)):
            raise ValueError(f"Null rate must be numeric, got {type(v)}")
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"Null rate must be between 0 and 1, got {v}")
        return float(v)


class TableMetric(BaseModel):
    """Metrics for a single table."""
    row_count: int = Field(ge=0, description="Total row count in table")
    freshness_minutes: int = Field(ge=0, description="Minutes since last data update")
    null_rates: Dict[str, float] = Field(description="Null rates per column")
    table_name: Optional[str] = Field(default=None, description="Name of the table")
    timestamp: Optional[datetime] = Field(default=None, description="Timestamp when metrics were collected")
    last_updated: Optional[str] = Field(default=None, description="ISO format timestamp of last update")

    @field_validator('null_rates')
    @classmethod
    def validate_null_rates_dict(cls, v):
        """Validate null rate values are between 0 and 1."""
        for col, rate in v.items():
            if not 0.0 <= rate <= 1.0:
                raise ValueError(f"Null rate for {col} must be between 0 and 1, got {rate}")
        return v


class DependencyMap(BaseModel):
    """Map of table dependencies."""
    model_config = ConfigDict(extra='allow')

    @field_validator('*', mode='before')
    @classmethod
    def validate_dependencies(cls, v):
        """Ensure dependencies are lists of strings."""
        if not isinstance(v, list):
            raise ValueError("Dependencies must be a list")
        if not all(isinstance(item, str) for item in v):
            raise ValueError("All dependencies must be strings")
        return v


class HistoricalBaseline(BaseModel):
    """Historical baseline statistics."""
    avg_daily_rows: int = Field(ge=0)
    avg_attribution_null_rate: float = Field(ge=0.0, le=1.0)


class CodeCommit(BaseModel):
    """Git commit information."""
    repo: str = Field(min_length=1)
    author: str = Field(min_length=1)
    message: str = Field(min_length=1)
    timestamp: str  # ISO 8601 format
    files_changed: List[str] = Field(min_items=0)

    @field_validator('timestamp')
    @classmethod
    def validate_timestamp(cls, v):
        """Validate ISO 8601 timestamp format."""
        try:
            datetime.fromisoformat(v.replace('Z', '+00:00'))
            return v
        except ValueError:
            raise ValueError(f"Invalid ISO 8601 timestamp: {v}")


class AlertHistoryEntry(BaseModel):
    """Historical alert record."""
    timestamp: str
    alert_type: str = Field(min_length=1)
    table: str = Field(min_length=1)
    resolution: str = Field(min_length=1)
    notes: str = Field(default="")

    @field_validator('timestamp')
    @classmethod
    def validate_timestamp(cls, v):
        """Validate ISO 8601 timestamp format."""
        try:
            datetime.fromisoformat(v.replace('Z', '+00:00'))
            return v
        except ValueError:
            raise ValueError(f"Invalid ISO 8601 timestamp: {v}")


class SLADefinition(BaseModel):
    """Service Level Agreement definition."""
    max_staleness_minutes: int = Field(ge=0)
    criticality: Criticality
    stakeholders: List[str] = Field(min_items=1)


class SystemMetadata(BaseModel):
    """System metadata."""
    domain: str = Field(min_length=1)
    environment: Literal["Production", "Staging", "Development"]
    timestamp: str

    @field_validator('timestamp')
    @classmethod
    def validate_timestamp(cls, v):
        """Validate ISO 8601 timestamp format."""
        try:
            datetime.fromisoformat(v.replace('Z', '+00:00'))
            return v
        except ValueError:
            raise ValueError(f"Invalid ISO 8601 timestamp: {v}")


class SystemState(BaseModel):
    """Complete system state snapshot."""
    metadata: SystemMetadata
    table_metrics: Dict[str, TableMetric]
    dependency_map: Dict[str, List[str]]
    historical_baseline_7d: Dict[str, HistoricalBaseline]
    pipeline_events: List[Dict[str, Any]] = Field(default_factory=list, description="Recent orchestration/observability signals")
    recent_code_commits: List[CodeCommit] = Field(default_factory=list)
    alert_history: List[AlertHistoryEntry] = Field(default_factory=list)
    sla_definitions: Dict[str, SLADefinition] = Field(default_factory=dict)


class ObservationPackage(BaseModel):
    """Package containing observation with telemetry."""
    telemetry: Dict[str, Any]
    payload: SystemState
    ml_predictions: Optional[Dict[str, Any]] = None
    rules_evaluation: Optional[Dict[str, Any]] = None


# -------------------------------------------------------------------------
# REASONER MODELS
# -------------------------------------------------------------------------

class Hypothesis(BaseModel):
    """Single hypothesis for root cause."""
    id: str = Field(pattern=r"^H\d+$", description="Hypothesis ID (e.g., H1, H2)")
    description: str = Field(min_length=10, description="Technical theory of root cause")
    supporting_evidence: str = Field(min_length=5, description="Why this hypothesis is plausible")
    confidence_score: float = Field(ge=0.0, le=100.0, description="Confidence percentage")


class InvestigationStep(BaseModel):
    """Single step in investigation plan."""
    step_id: int = Field(ge=1)
    action: str = Field(min_length=1, description="Tool or action to execute")
    target: Optional[str] = Field(default=None, description="Target system/service")
    args: Dict[str, Any] = Field(default_factory=dict, description="Arguments for the action")


class ReasoningOutput(BaseModel):
    """Output from the Reasoner component."""
    analysis_summary: str = Field(min_length=10)
    detected_anomalies: List[str] = Field(min_items=0)
    hypotheses: List[Hypothesis] = Field(min_items=1, max_items=10)
    investigation_plan: List[InvestigationStep] = Field(min_items=1)
    severity_assessment: Criticality


class ReasoningResult(BaseModel):
    """Complete reasoning result with metadata."""
    metadata: Dict[str, Any]
    reasoning: ReasoningOutput


# -------------------------------------------------------------------------
# INVESTIGATOR MODELS
# -------------------------------------------------------------------------

class ToolResult(BaseModel):
    """Result from executing an investigation tool."""
    tool: str = Field(min_length=1)
    status: str = Field(min_length=1)
    model_config = ConfigDict(extra='allow')  # Allow additional fields


class EvidenceItem(BaseModel):
    """Single piece of evidence collected."""
    step_id: int = Field(ge=1)
    action: str = Field(min_length=1)
    evidence: ToolResult


# -------------------------------------------------------------------------
# VERIFIER MODELS
# -------------------------------------------------------------------------

class VerificationResult(BaseModel):
    """Result from verification phase for the UI."""
    is_verified: bool
    verification_confidence: float = Field(ge=0.0, le=100.0)
    verification_evidence: Any = Field(default=None)
    summary: str


class IncidentReport(BaseModel):
    """Final incident report after verification."""
    report_id: str = Field(pattern=r"^[a-f0-9-]{36}$", description="UUID format")
    timestamp: str
    cycle_id: int = Field(default=0)
    incident_type: IncidentType
    status: str = Field(default="DETECTED", description="Current status of the incident")
    llm_provider: Optional[str] = Field(default=None, description="LLM provider used for reasoning/verification")
    llm_model: Optional[str] = Field(default=None, description="LLM model name used for reasoning/verification")
    confidence_threshold: Optional[float] = Field(default=None, description="Configured confidence threshold at runtime")
    trigger_signals: List[str] = Field(default_factory=list, description="High-level signals that triggered investigation")
    hypothesis: str = Field(default="", description="To match frontend expectation")
    primary_hypothesis: str = Field(min_length=10)
    verification_status: VerificationStatus
    verification_result: Optional[VerificationResult] = None
    final_confidence_score: float = Field(ge=0.0, le=100.0)
    root_cause_analysis: str = Field(min_length=10)
    root_cause_category: RootCauseCategory = Field(default=RootCauseCategory.UNKNOWN)
    mitigation_status: str = Field(default="PENDING")
    evidence_summary: List[str] = Field(min_items=1)
    anomaly_evidence: Any = Field(default=None)
    recommended_actions: List[str] = Field(default_factory=list)
    affected_downstream_systems: List[str] = Field(default_factory=list)
    decision_log: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Structured reasoning trace / decision log across the agent loop (triage, plan, verify, policies, remediation risk).",
    )

    @field_validator('timestamp')
    @classmethod
    def validate_timestamp(cls, v):
        """Validate ISO 8601 timestamp format."""
        try:
            datetime.fromisoformat(v.replace('Z', '+00:00'))
            return v
        except ValueError:
            raise ValueError(f"Invalid ISO 8601 timestamp: {v}")


# -------------------------------------------------------------------------
# TELEMETRY MODELS
# -------------------------------------------------------------------------

class Telemetry(BaseModel):
    """Telemetry data for observability."""
    trace_id: str = Field(pattern=r"^[a-f0-9-]{36}$")
    latency_ms: float = Field(ge=0.0)
    component: str = Field(min_length=1)
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    timestamp: Optional[str] = None

    @field_validator('timestamp')
    @classmethod
    def validate_timestamp(cls, v):
        """Validate ISO 8601 timestamp format if provided."""
        if v is None:
            return v
        try:
            datetime.fromisoformat(v.replace('Z', '+00:00'))
            return v
        except ValueError:
            raise ValueError(f"Invalid ISO 8601 timestamp: {v}")


# -------------------------------------------------------------------------
# META-LEARNING MODELS
# -------------------------------------------------------------------------

class PatternInsight(BaseModel):
    """Pattern detected by meta-learning."""
    culprit_service: str
    frequency: int = Field(ge=0)
    pattern_signature: str


class MetaAnalysisReport(BaseModel):
    """Meta-analysis report."""
    period_analyzed: str
    total_incidents: int = Field(ge=0)
    most_frequent_type: str
    detected_pattern: PatternInsight
    recommendation: str = Field(min_length=10)
