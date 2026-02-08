"""
Tenant Models - Multi-tenancy data models
Defines tenant structure and configuration.
"""
from pydantic import BaseModel, Field, field_validator
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum


class TenantStatus(Enum):
    """Status of a tenant."""
    ACTIVE = "active"
    SUSPENDED = "suspended"
    INACTIVE = "inactive"


class DataSourceConfig(BaseModel):
    """Configuration for a tenant's data source."""
    type: str = Field(description="Data source type (sqlite, bigquery, snowflake, postgres, mysql)")

    # Generic SQL sources
    host: Optional[str] = Field(default=None, description="Database host")
    port: Optional[int] = Field(default=None, description="Database port")
    database: Optional[str] = Field(default=None, description="Database name")
    username: Optional[str] = Field(default=None, description="Database username")
    password: Optional[str] = Field(default=None, description="Database password or secret reference")

    # SQLite
    sqlite_path: Optional[str] = Field(default=None, description="SQLite database path")

    # BigQuery
    bigquery_project_id: Optional[str] = Field(default=None, description="BigQuery project ID")
    bigquery_credentials_path: Optional[str] = Field(default=None, description="Service account JSON path (optional)")
    bigquery_dataset: Optional[str] = Field(default=None, description="Default dataset (optional)")

    # Snowflake
    snowflake_account: Optional[str] = Field(default=None, description="Snowflake account identifier")
    snowflake_user: Optional[str] = Field(default=None, description="Snowflake username")
    snowflake_password: Optional[str] = Field(default=None, description="Snowflake password or secret reference")
    snowflake_warehouse: Optional[str] = Field(default=None, description="Snowflake warehouse")
    snowflake_database: Optional[str] = Field(default=None, description="Snowflake database")
    snowflake_schema: Optional[str] = Field(default=None, description="Snowflake schema (default: PUBLIC)")
    snowflake_role: Optional[str] = Field(default=None, description="Snowflake role (optional)")

    @field_validator('type')
    @classmethod
    def validate_type(cls, v):
        """Validate data source type."""
        allowed_types = ['postgres', 'mysql', 'sqlite', 'bigquery', 'snowflake']
        if v.lower() not in allowed_types:
            raise ValueError(f"Data source type must be one of: {', '.join(allowed_types)}")
        return v.lower()

    @field_validator('sqlite_path', mode='after')
    @classmethod
    def validate_required_fields(cls, v, info):
        # Pydantic v2: use info.data for other fields
        data = getattr(info, "data", {}) or {}
        t = str(data.get("type") or "").lower()

        if t == "sqlite":
            if not (data.get("sqlite_path") or data.get("database")):
                raise ValueError("sqlite requires sqlite_path (or database)")
        elif t == "bigquery":
            if not data.get("bigquery_project_id"):
                raise ValueError("bigquery requires bigquery_project_id")
        elif t == "snowflake":
            required = ["snowflake_account", "snowflake_user", "snowflake_password", "snowflake_warehouse", "snowflake_database"]
            missing = [k for k in required if not data.get(k)]
            if missing:
                raise ValueError(f"snowflake missing required fields: {', '.join(missing)}")
        elif t in ("postgres", "mysql"):
            required = ["host", "port", "database", "username"]
            missing = [k for k in required if not data.get(k)]
            if missing:
                raise ValueError(f"{t} missing required fields: {', '.join(missing)}")
        return v


class TenantConfig(BaseModel):
    """Tenant-specific configuration."""
    # Data sources
    data_sources: List[DataSourceConfig] = Field(default_factory=list, description="List of data sources")

    # Alert configuration
    alert_channels: List[str] = Field(default_factory=list, description="Alert channels (email, slack, etc.)")
    confidence_threshold: float = Field(default=85.0, ge=0.0, le=100.0, description="Confidence threshold for alerts")

    # System limits
    max_cycles: int = Field(default=1000, ge=1, description="Maximum cycles allowed")
    max_incidents_stored: int = Field(default=10000, ge=100, description="Maximum incidents to store")

    # Feature flags
    enable_ml: bool = Field(default=False, description="Enable ML anomaly detection")
    enable_remediation: bool = Field(default=False, description="Enable automated remediation")
    enable_notifications: bool = Field(default=True, description="Enable notifications")

    # Custom settings
    custom_settings: Dict[str, Any] = Field(default_factory=dict, description="Custom tenant-specific settings")


class Tenant(BaseModel):
    """Represents a tenant in the multi-tenant system."""
    id: str = Field(pattern=r'^[a-z0-9-]+$', description="Tenant ID (lowercase alphanumeric with hyphens)")
    name: str = Field(min_length=1, max_length=255, description="Tenant display name")
    config: TenantConfig = Field(default_factory=TenantConfig, description="Tenant configuration")
    status: TenantStatus = Field(default=TenantStatus.ACTIVE, description="Tenant status")
    created_at: datetime = Field(default_factory=datetime.now, description="Creation timestamp")
    updated_at: Optional[datetime] = Field(default=None, description="Last update timestamp")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    @field_validator('id')
    @classmethod
    def validate_tenant_id(cls, v):
        """Validate tenant ID format."""
        if len(v) < 3:
            raise ValueError("Tenant ID must be at least 3 characters")
        if len(v) > 50:
            raise ValueError("Tenant ID must be at most 50 characters")
        if v.startswith('-') or v.endswith('-'):
            raise ValueError("Tenant ID cannot start or end with hyphen")
        return v

    def is_active(self) -> bool:
        """Check if tenant is active."""
        return self.status == TenantStatus.ACTIVE

    def to_dict(self) -> Dict[str, Any]:
        """Convert tenant to dictionary."""
        return {
            'id': self.id,
            'name': self.name,
            'config': self.config.model_dump(),
            'status': self.status.value,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'metadata': self.metadata
        }


class TenantCreate(BaseModel):
    """Request model for creating a tenant."""
    id: str = Field(pattern=r'^[a-z0-9-]+$')
    name: str = Field(min_length=1, max_length=255)
    config: Optional[TenantConfig] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TenantUpdate(BaseModel):
    """Request model for updating a tenant."""
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    config: Optional[TenantConfig] = None
    status: Optional[TenantStatus] = None
    metadata: Optional[Dict[str, Any]] = None
