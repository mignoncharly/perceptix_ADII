"""
Rule Models

Defines data models for custom alerting rules.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
import re


class RulePriority(str, Enum):
    """Priority levels for rules."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ConditionOperator(str, Enum):
    """Operators for condition evaluation."""
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    GREATER_THAN = "greater_than"
    GREATER_THAN_OR_EQUAL = "greater_than_or_equal"
    LESS_THAN = "less_than"
    LESS_THAN_OR_EQUAL = "less_than_or_equal"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    IN = "in"
    NOT_IN = "not_in"
    REGEX = "regex"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"


class Condition(BaseModel):
    """
    A single condition in a rule.

    Example:
        field: "null_rates.attribution_source"
        operator: "greater_than"
        value: 0.5
    """
    field: str = Field(..., description="Field path to evaluate (e.g., 'table_name' or 'null_rates.column')")
    operator: ConditionOperator = Field(..., description="Comparison operator")
    value: Any = Field(..., description="Value to compare against")

    @field_validator('field')
    @classmethod
    def validate_field(cls, v: str) -> str:
        """Validate field path."""
        if not v or not isinstance(v, str):
            raise ValueError("Field must be a non-empty string")
        return v

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "field": self.field,
            "operator": self.operator.value,
            "value": self.value
        }


class RuleConditions(BaseModel):
    """
    Logical conditions for rule matching.
    Supports AND/OR/NOT logic.
    """
    all: Optional[List[Condition]] = Field(None, description="All conditions must match (AND)")
    any: Optional[List[Condition]] = Field(None, description="At least one condition must match (OR)")
    none: Optional[List[Condition]] = Field(None, description="No conditions must match (NOT)")

    @field_validator('all', 'any', 'none')
    @classmethod
    def validate_conditions_list(cls, v):
        """Ensure at least one condition group is provided."""
        if v is not None and len(v) == 0:
            raise ValueError("Condition list cannot be empty if provided")
        return v

    def has_conditions(self) -> bool:
        """Check if any conditions are defined."""
        return bool(self.all or self.any or self.none)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {}
        if self.all:
            result["all"] = [c.to_dict() for c in self.all]
        if self.any:
            result["any"] = [c.to_dict() for c in self.any]
        if self.none:
            result["none"] = [c.to_dict() for c in self.none]
        return result


class RuleAction(BaseModel):
    """
    Action to execute when rule triggers.
    """
    type: str = Field(..., description="Action type (e.g., 'alert', 'auto_investigate')")
    params: Dict[str, Any] = Field(default_factory=dict, description="Action parameters")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "type": self.type,
            "params": self.params
        }


class AlertRule(BaseModel):
    """
    User-defined alerting rule.
    """
    id: str = Field(..., description="Unique rule identifier")
    name: str = Field(..., description="Human-readable rule name")
    description: str = Field(default="", description="Rule description")
    enabled: bool = Field(default=True, description="Whether rule is active")
    priority: RulePriority = Field(default=RulePriority.MEDIUM, description="Rule priority")

    conditions: RuleConditions = Field(..., description="Conditions for rule matching")
    actions: List[RuleAction] = Field(..., description="Actions to execute when triggered")

    cooldown_minutes: int = Field(default=60, description="Cooldown period between triggers")
    max_triggers_per_day: int = Field(default=10, description="Maximum triggers per day")

    tags: List[str] = Field(default_factory=list, description="Tags for categorization")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @field_validator('id')
    @classmethod
    def validate_id(cls, v: str) -> str:
        """Validate rule ID format."""
        if not re.match(r'^[a-z0-9_-]+$', v):
            raise ValueError("Rule ID must contain only lowercase letters, numbers, hyphens, and underscores")
        return v

    @field_validator('actions')
    @classmethod
    def validate_actions(cls, v: List[RuleAction]) -> List[RuleAction]:
        """Ensure at least one action is defined."""
        if not v or len(v) == 0:
            raise ValueError("At least one action must be defined")
        return v

    @field_validator('cooldown_minutes')
    @classmethod
    def validate_cooldown(cls, v: int) -> int:
        """Validate cooldown period."""
        if v < 0:
            raise ValueError("Cooldown must be non-negative")
        return v

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled,
            "priority": self.priority.value,
            "conditions": self.conditions.to_dict(),
            "actions": [a.to_dict() for a in self.actions],
            "cooldown_minutes": self.cooldown_minutes,
            "max_triggers_per_day": self.max_triggers_per_day,
            "tags": self.tags,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }


class RuleEvaluationResult(BaseModel):
    """
    Result of evaluating a rule.
    """
    rule_id: str
    matched: bool
    conditions_met: Dict[str, bool] = Field(default_factory=dict)
    evaluation_time: datetime = Field(default_factory=datetime.now)
    context_snapshot: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None


class ActionResult(BaseModel):
    """
    Result of executing an action.
    """
    action_type: str
    success: bool
    message: str = ""
    details: Dict[str, Any] = Field(default_factory=dict)
    execution_time: datetime = Field(default_factory=datetime.now)


class ValidationResult(BaseModel):
    """
    Result of validating a rule.
    """
    valid: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
