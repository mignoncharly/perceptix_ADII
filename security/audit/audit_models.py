"""
Audit Event Models

Data models for audit logging.
"""

from enum import Enum
from datetime import datetime
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field


class AuditEventType(str, Enum):
    """Types of audit events."""
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    CONFIGURATION_CHANGE = "configuration_change"
    DATA_ACCESS = "data_access"
    INCIDENT_INVESTIGATION = "incident_investigation"
    REMEDIATION_ACTION = "remediation_action"
    API_CALL = "api_call"
    CYCLE_TRIGGER = "cycle_trigger"
    RULE_MODIFICATION = "rule_modification"
    SECRET_ACCESS = "secret_access"
    SYSTEM_EVENT = "system_event"


class AuditEvent(BaseModel):
    """Audit event model."""

    event_id: str = Field(default_factory=lambda: __import__('uuid').uuid4().hex)
    timestamp: datetime = Field(default_factory=datetime.now)
    event_type: AuditEventType
    user: str
    action: str
    resource: str
    status: str  # success, failure, denied
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'event_id': self.event_id,
            'timestamp': self.timestamp.isoformat(),
            'event_type': self.event_type.value,
            'user': self.user,
            'action': self.action,
            'resource': self.resource,
            'status': self.status,
            'ip_address': self.ip_address,
            'user_agent': self.user_agent,
            'details': self.details
        }

    def to_syslog_format(self) -> str:
        """Convert to syslog-compatible format."""
        return (
            f"<134>1 {self.timestamp.isoformat()} cognizant {self.event_type.value} "
            f"- - - user={self.user} action={self.action} resource={self.resource} "
            f"status={self.status} ip={self.ip_address or 'N/A'}"
        )
