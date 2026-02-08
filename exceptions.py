"""
Custom Exception Hierarchy for Perceptix System
Provides structured error handling with context preservation.
"""
from typing import Optional, Dict, Any


class PerceptixError(Exception):
    """Base exception for all Perceptix errors."""

    def __init__(
        self,
        message: str,
        component: Optional[str] = None,
        trace_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.component = component
        self.trace_id = trace_id
        self.context = context or {}
        super().__init__(self.message)

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for structured logging."""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "component": self.component,
            "trace_id": self.trace_id,
            "context": self.context
        }


# -------------------------------------------------------------------------
# CONFIGURATION ERRORS
# -------------------------------------------------------------------------

class ConfigurationError(PerceptixError):
    """Raised when configuration is invalid or missing."""
    pass


class InvalidAPIKeyError(ConfigurationError):
    """Raised when API key is invalid or not found."""
    pass


class InvalidModeError(ConfigurationError):
    """Raised when system mode is invalid."""
    pass


# -------------------------------------------------------------------------
# ML/FEATURE ENGINEERING ERRORS
# -------------------------------------------------------------------------

class MLModelError(PerceptixError):
    """Raised when ML model operations fail."""
    pass


class FeatureEngineeringError(PerceptixError):
    """Raised when feature extraction fails."""
    pass


# -------------------------------------------------------------------------
# VALIDATION ERRORS
# -------------------------------------------------------------------------

class ValidationError(PerceptixError):
    """Raised when data validation fails."""
    pass


class InvalidSystemStateError(ValidationError):
    """Raised when system state data is invalid."""
    pass


class InvalidHypothesisError(ValidationError):
    """Raised when hypothesis data is malformed."""
    pass


# -------------------------------------------------------------------------
# OBSERVER ERRORS
# -------------------------------------------------------------------------

class ObserverError(PerceptixError):
    """Base class for Observer component errors."""
    pass


class DataSourceConnectionError(ObserverError):
    """Raised when unable to connect to data source."""
    pass


class DataFetchError(ObserverError):
    """Raised when data fetching fails."""
    pass


# -------------------------------------------------------------------------
# REASONER ERRORS
# -------------------------------------------------------------------------

class ReasonerError(PerceptixError):
    """Base class for Reasoner component errors."""
    pass


class APICallError(ReasonerError):
    """Raised when API call to LLM fails."""
    pass


class ResponseParsingError(ReasonerError):
    """Raised when LLM response cannot be parsed."""
    pass


class InvalidResponseFormatError(ReasonerError):
    """Raised when LLM response has invalid structure."""
    pass


class TokenLimitExceededError(ReasonerError):
    """Raised when prompt exceeds token limits."""
    pass


# -------------------------------------------------------------------------
# INVESTIGATOR ERRORS
# -------------------------------------------------------------------------

class InvestigatorError(PerceptixError):
    """Base class for Investigator component errors."""
    pass


class ToolExecutionError(InvestigatorError):
    """Raised when investigation tool execution fails."""
    pass


class UnknownToolError(InvestigatorError):
    """Raised when unknown tool is requested."""
    pass


class GitAPIError(InvestigatorError):
    """Raised when Git API interactions fail."""
    pass


# -------------------------------------------------------------------------
# VERIFIER ERRORS
# -------------------------------------------------------------------------

class VerifierError(PerceptixError):
    """Base class for Verifier component errors."""
    pass


class InsufficientEvidenceError(VerifierError):
    """Raised when evidence is insufficient for verification."""
    pass


# -------------------------------------------------------------------------
# DATABASE ERRORS
# -------------------------------------------------------------------------

class DatabaseError(PerceptixError):
    """Base class for database-related errors."""
    pass


class ConnectionPoolExhaustedError(DatabaseError):
    """Raised when database connection pool is exhausted."""
    pass


class TransactionError(DatabaseError):
    """Raised when database transaction fails."""
    pass


class QueryExecutionError(DatabaseError):
    """Raised when database query execution fails."""
    pass


# -------------------------------------------------------------------------
# HISTORIAN ERRORS
# -------------------------------------------------------------------------

class HistorianError(PerceptixError):
    """Base class for Historian component errors."""
    pass


class IncidentStorageError(HistorianError):
    """Raised when incident cannot be stored."""
    pass


class IncidentRetrievalError(HistorianError):
    """Raised when incident retrieval fails."""
    pass


# -------------------------------------------------------------------------
# ESCALATOR ERRORS
# -------------------------------------------------------------------------

class EscalatorError(PerceptixError):
    """Base class for Escalator component errors."""
    pass


class NotificationError(EscalatorError):
    """Raised when notification delivery fails."""
    pass


class AlertRoutingError(EscalatorError):
    """Raised when alert cannot be routed to correct channel."""
    pass


# -------------------------------------------------------------------------
# META-LEARNER ERRORS
# -------------------------------------------------------------------------

class MetaLearnerError(PerceptixError):
    """Base class for Meta-Learner component errors."""
    pass


class PatternAnalysisError(MetaLearnerError):
    """Raised when pattern analysis fails."""
    pass


# -------------------------------------------------------------------------
# SYSTEM ERRORS
# -------------------------------------------------------------------------

class SystemError(PerceptixError):
    """Critical system-level errors."""
    pass


class ComponentInitializationError(SystemError):
    """Raised when component fails to initialize."""
    pass


class CycleLimitExceededError(SystemError):
    """Raised when system exceeds maximum cycle limit."""
    pass


# -------------------------------------------------------------------------
# REMEDIATION ERRORS
# -------------------------------------------------------------------------

class RemediationError(PerceptixError):
    """Base class for Remediation component errors."""
    pass


class PlaybookExecutionError(RemediationError):
    """Raised when playbook execution fails."""
    pass


class ActionExecutionError(RemediationError):
    """Raised when action execution fails."""
    pass


class ApprovalTimeoutError(RemediationError):
    """Raised when approval request times out."""
    pass


class PlaybookNotFoundError(RemediationError):
    """Raised when requested playbook is not found."""
    pass
