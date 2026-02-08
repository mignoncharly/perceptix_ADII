"""
Base Action Classes and Registry
Defines the interface for all remediation actions.
"""
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Type
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


logger = logging.getLogger("RemediationActions")


class ActionStatus(Enum):
    """Status of an action execution."""
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    REQUIRES_APPROVAL = "requires_approval"


@dataclass
class ActionResult:
    """Result of an action execution."""
    status: ActionStatus
    message: str
    action_name: str
    timestamp: datetime
    details: Dict[str, Any]
    error: Optional[str] = None
    rollback_data: Optional[Dict[str, Any]] = None


class Action(ABC):
    """
    Base class for all remediation actions.

    Each action must implement:
    - execute(): Perform the action
    - rollback(): Undo the action
    - validate_params(): Validate action parameters
    """

    def __init__(self, name: str, description: str = ""):
        """
        Initialize action.

        Args:
            name: Action name
            description: Action description
        """
        self.name = name
        self.description = description
        self.logger = logging.getLogger(f"Action.{name}")

    @abstractmethod
    def execute(self, params: Dict[str, Any]) -> ActionResult:
        """
        Execute the action.

        Args:
            params: Action parameters from playbook

        Returns:
            ActionResult with execution status
        """
        raise NotImplementedError

    @abstractmethod
    def rollback(self, rollback_data: Dict[str, Any]) -> ActionResult:
        """
        Rollback the action.

        Args:
            rollback_data: Data needed to rollback the action

        Returns:
            ActionResult with rollback status
        """
        raise NotImplementedError

    @abstractmethod
    def validate_params(self, params: Dict[str, Any]) -> bool:
        """
        Validate action parameters.

        Args:
            params: Parameters to validate

        Returns:
            True if valid, False otherwise
        """
        raise NotImplementedError

    def is_destructive(self) -> bool:
        """
        Check if action is destructive (requires approval).

        Returns:
            True if destructive, False otherwise
        """
        destructive_keywords = ["delete", "drop", "truncate", "remove", "destroy"]
        return any(keyword in self.name.lower() for keyword in destructive_keywords)


class ActionRegistry:
    """
    Registry of all available remediation actions.
    Manages action lifecycle and execution.
    """

    def __init__(self):
        """Initialize action registry."""
        self.actions: Dict[str, Type[Action]] = {}
        self.logger = logging.getLogger("ActionRegistry")
        self._register_default_actions()

    def _register_default_actions(self):
        """Register default built-in actions."""
        # Actions will be registered as they're implemented
        pass

    def register(self, action_name: str, action_class: Type[Action]):
        """
        Register a new action.

        Args:
            action_name: Name to register action under
            action_class: Action class to register
        """
        if not issubclass(action_class, Action):
            raise ValueError(f"{action_class} must be a subclass of Action")

        self.actions[action_name] = action_class
        self.logger.info(f"Registered action: {action_name}")

    def get_action(self, action_name: str, **kwargs) -> Optional[Action]:
        """
        Get an action instance by name.

        Args:
            action_name: Name of action to retrieve
            **kwargs: Arguments to pass to action constructor

        Returns:
            Action instance or None if not found
        """
        action_class = self.actions.get(action_name)
        if not action_class:
            self.logger.error(f"Action not found: {action_name}")
            return None

        try:
            return action_class(**kwargs)
        except Exception:
            # Use exception() so we get full traceback in DEBUG logs
            self.logger.exception(f"Failed to instantiate action {action_name}")
            return None

    def list_actions(self) -> list[str]:
        """
        List all registered actions.

        Returns:
            List of action names
        """
        return list(self.actions.keys())

    def execute_action(self, action_name: str, params: Dict[str, Any], **kwargs) -> ActionResult:
        """
        Execute an action by name.

        Args:
            action_name: Name of action to execute
            params: Parameters for the action
            **kwargs: Additional arguments for action constructor

        Returns:
            ActionResult with execution status
        """
        action = self.get_action(action_name, **kwargs)

        if not action:
            result = ActionResult(
                status=ActionStatus.FAILED,
                message=f"Action not found: {action_name}",
                action_name=action_name,
                timestamp=datetime.now(),
                details={"params": params},
                error=f"Action '{action_name}' not registered",
            )
            self.logger.error(f"Action {action_name} failed: {result.error}")
            return result

        # Validate parameters
        try:
            if not action.validate_params(params):
                result = ActionResult(
                    status=ActionStatus.FAILED,
                    message=f"Invalid parameters for action: {action_name}",
                    action_name=action_name,
                    timestamp=datetime.now(),
                    details={"params": params},
                    error="Parameter validation failed",
                )
                self.logger.error(
                    f"Action {action_name} failed validation: {result.message} | details={result.details}"
                )
                return result
        except Exception as e:
            result = ActionResult(
                status=ActionStatus.FAILED,
                message=f"Parameter validation error: {str(e)}",
                action_name=action_name,
                timestamp=datetime.now(),
                details={"params": params},
                error=f"{type(e).__name__}: {str(e)}",
            )
            self.logger.exception(f"Action {action_name} validation raised exception")
            return result

        # Execute action
        self.logger.info(f"Executing action: {action_name}")
        try:
            result = action.execute(params)
        except Exception as e:
            # If action code throws instead of returning ActionResult, capture it
            self.logger.exception(f"Action {action_name} threw exception during execute()")
            result = ActionResult(
                status=ActionStatus.FAILED,
                message=f"Action execution failed: {str(e)}",
                action_name=action_name,
                timestamp=datetime.now(),
                details={"params": params},
                error=f"{type(e).__name__}: {str(e)}",
            )

        # IMPORTANT: log failure details (this is what you were missing)
        if result.status == ActionStatus.FAILED:
            self.logger.error(
                f"Action {action_name} completed with status: {result.status.value} | "
                f"message={result.message} | error={result.error} | details={result.details}"
            )
        else:
            self.logger.info(f"Action {action_name} completed with status: {result.status.value}")

        return result


# Create global registry instance
_global_registry = ActionRegistry()


def get_global_registry() -> ActionRegistry:
    """
    Get the global action registry instance.

    Returns:
        Global ActionRegistry instance
    """
    return _global_registry
