"""
Playbook Executor - Loads and executes remediation playbooks
Handles YAML playbook parsing and step-by-step execution.
"""
import yaml
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from remediation.actions.base import ActionRegistry, ActionResult, ActionStatus, get_global_registry


logger = logging.getLogger("PlaybookExecutor")


@dataclass
class PlaybookStep:
    """Single step in a playbook."""
    name: str
    action: str
    params: Dict[str, Any]


@dataclass
class Playbook:
    """Complete playbook definition."""
    name: str
    description: str
    triggers: List[Dict[str, Any]]
    conditions: List[Dict[str, str]]
    steps: List[PlaybookStep]
    rollback: List[PlaybookStep]


@dataclass
class PlaybookExecution:
    """Result of playbook execution."""
    playbook_name: str
    success: bool
    steps_executed: int
    steps_failed: int
    execution_time_ms: float
    step_results: List[ActionResult]
    error: Optional[str] = None
    rollback_executed: bool = False


class PlaybookExecutor:
    """
    Executes remediation playbooks step-by-step.
    """

    def __init__(self, action_registry: Optional[ActionRegistry] = None):
        """
        Initialize playbook executor.

        Args:
            action_registry: Optional action registry (uses global if None)
        """
        self.action_registry = action_registry or get_global_registry()
        self.logger = logging.getLogger("PlaybookExecutor")
        self.playbooks: Dict[str, Playbook] = {}

    def load_playbook(self, playbook_path: str) -> Optional[Playbook]:
        """
        Load playbook from YAML file.

        Args:
            playbook_path: Path to playbook YAML file

        Returns:
            Playbook object or None if failed
        """
        try:
            with open(playbook_path, 'r') as f:
                data = yaml.safe_load(f)

            # Parse playbook structure
            name = data.get('name', 'Unnamed Playbook')
            description = data.get('description', '')
            triggers = data.get('triggers', [])
            conditions = data.get('conditions', [])

            # Parse steps
            steps = []
            for step_data in data.get('steps', []):
                step = PlaybookStep(
                    name=step_data.get('name', 'Unnamed Step'),
                    action=step_data.get('action'),
                    params=step_data.get('params', {})
                )
                steps.append(step)

            # Parse rollback steps
            rollback = []
            for step_data in data.get('rollback', []):
                step = PlaybookStep(
                    name=step_data.get('name', 'Unnamed Rollback Step'),
                    action=step_data.get('action'),
                    params=step_data.get('params', {})
                )
                rollback.append(step)

            playbook = Playbook(
                name=name,
                description=description,
                triggers=triggers,
                conditions=conditions,
                steps=steps,
                rollback=rollback
            )

            # Store in registry
            self.playbooks[name] = playbook

            self.logger.info(f"Loaded playbook: {name} ({len(steps)} steps)")
            return playbook

        except Exception as e:
            self.logger.error(f"Failed to load playbook {playbook_path}: {e}")
            return None

    def load_playbooks_from_directory(self, directory: str) -> int:
        """
        Load all playbooks from a directory.

        Args:
            directory: Directory containing playbook YAML files

        Returns:
            Number of playbooks loaded
        """
        count = 0
        playbook_dir = Path(directory)

        if not playbook_dir.exists():
            self.logger.warning(f"Playbook directory not found: {directory}")
            return 0

        for yaml_file in playbook_dir.glob('*.yaml'):
            playbook = self.load_playbook(str(yaml_file))
            if playbook:
                count += 1

        for yml_file in playbook_dir.glob('*.yml'):
            playbook = self.load_playbook(str(yml_file))
            if playbook:
                count += 1

        self.logger.info(f"Loaded {count} playbooks from {directory}")
        return count

    def matches_trigger(
        self,
        playbook: Playbook,
        incident_type: str,
        confidence: float
    ) -> bool:
        """
        Check if incident matches playbook triggers.

        Args:
            playbook: Playbook to check
            incident_type: Type of incident
            confidence: Confidence score

        Returns:
            True if matches, False otherwise
        """
        for trigger in playbook.triggers:
            trigger_type = trigger.get('incident_type', '').upper()
            min_confidence = trigger.get('confidence_threshold', 0)

            if incident_type.upper() == trigger_type and confidence >= min_confidence:
                return True

        return False

    def check_conditions(self, playbook: Playbook, context: Dict[str, Any]) -> bool:
        """
        Check if all playbook conditions are met.

        Args:
            playbook: Playbook to check
            context: Execution context

        Returns:
            True if all conditions met, False otherwise
        """
        for condition in playbook.conditions:
            check_name = condition.get('check')

            # Simple condition checking (can be extended)
            if check_name == 'git_diff_available':
                # Check if git is available and has changes
                # For now, always return True
                continue
            elif check_name == 'etl_config_editable':
                # Check if ETL config file is writable
                # For now, always return True
                continue
            else:
                self.logger.warning(f"Unknown condition: {check_name}")
                # Unknown conditions pass by default
                continue

        return True

    def execute_playbook(
        self,
        playbook: Playbook,
        context: Dict[str, Any],
        dry_run: bool = False
    ) -> PlaybookExecution:
        """
        Execute a playbook.

        Args:
            playbook: Playbook to execute
            context: Execution context (variables to substitute)
            dry_run: If True, simulate execution without making changes

        Returns:
            PlaybookExecution result
        """
        start_time = datetime.now()
        step_results: List[ActionResult] = []
        steps_executed = 0
        steps_failed = 0
        rollback_data: List[Dict[str, Any]] = []

        self.logger.info(f"Executing playbook: {playbook.name} (dry_run={dry_run})")

        try:
            # Execute each step
            for i, step in enumerate(playbook.steps):
                self.logger.info(f"Step {i+1}/{len(playbook.steps)}: {step.name}")

                if dry_run:
                    # Simulate execution
                    result = ActionResult(
                        status=ActionStatus.SUCCESS,
                        message=f"[DRY RUN] Would execute: {step.action}",
                        action_name=step.action,
                        timestamp=datetime.now(),
                        details={"params": step.params, "dry_run": True}
                    )
                else:
                    # Substitute context variables in params
                    substituted_params = self._substitute_variables(step.params, context)

                    # Execute action
                    result = self.action_registry.execute_action(
                        action_name=step.action,
                        params=substituted_params
                    )

                step_results.append(result)
                steps_executed += 1

                # Store rollback data
                if result.rollback_data:
                    rollback_data.append({
                        'step_index': i,
                        'action': step.action,
                        'rollback_data': result.rollback_data
                    })

                # Check if step failed
                if result.status == ActionStatus.FAILED:
                    steps_failed += 1
                    self.logger.error(f"Step failed: {step.name}")

                    # Execute rollback if not dry run
                    if not dry_run and rollback_data:
                        self.logger.info("Executing rollback...")
                        self._execute_rollback(playbook, rollback_data)

                    # Stop execution on failure
                    break

            # Calculate execution time
            end_time = datetime.now()
            execution_time_ms = (end_time - start_time).total_seconds() * 1000

            success = steps_failed == 0

            return PlaybookExecution(
                playbook_name=playbook.name,
                success=success,
                steps_executed=steps_executed,
                steps_failed=steps_failed,
                execution_time_ms=execution_time_ms,
                step_results=step_results,
                rollback_executed=not success and not dry_run
            )

        except Exception as e:
            self.logger.error(f"Playbook execution failed: {e}")

            end_time = datetime.now()
            execution_time_ms = (end_time - start_time).total_seconds() * 1000

            return PlaybookExecution(
                playbook_name=playbook.name,
                success=False,
                steps_executed=steps_executed,
                steps_failed=steps_failed + 1,
                execution_time_ms=execution_time_ms,
                step_results=step_results,
                error=str(e),
                rollback_executed=False
            )

    def _execute_rollback(
        self,
        playbook: Playbook,
        rollback_data: List[Dict[str, Any]]
    ):
        """
        Execute rollback steps.

        Args:
            playbook: Playbook being rolled back
            rollback_data: Rollback data from executed steps
        """
        self.logger.info(f"Rolling back {len(rollback_data)} steps")

        # Execute in reverse order
        for data in reversed(rollback_data):
            action_name = data['action']
            step_rollback_data = data['rollback_data']

            try:
                action = self.action_registry.get_action(action_name)
                if action:
                    result = action.rollback(step_rollback_data)
                    self.logger.info(f"Rollback step completed: {result.status.value}")
                else:
                    self.logger.error(f"Action not found for rollback: {action_name}")
            except Exception as e:
                self.logger.error(f"Rollback failed for {action_name}: {e}")

    def _substitute_variables(
        self,
        params: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Substitute variables in parameters using context.

        Args:
            params: Parameters with {{variable}} placeholders
            context: Context variables

        Returns:
            Parameters with substituted values
        """
        import re

        def substitute_value(value: Any) -> Any:
            if isinstance(value, str):
                # Replace {{variable}} with context value
                pattern = r'\{\{(\w+)\}\}'
                matches = re.findall(pattern, value)
                for var_name in matches:
                    if var_name in context:
                        value = value.replace(f'{{{{{var_name}}}}}', str(context[var_name]))
                return value
            elif isinstance(value, dict):
                return {k: substitute_value(v) for k, v in value.items()}
            elif isinstance(value, list):
                return [substitute_value(item) for item in value]
            else:
                return value

        return substitute_value(params)

    def get_playbook(self, name: str) -> Optional[Playbook]:
        """
        Get a playbook by name.

        Args:
            name: Playbook name

        Returns:
            Playbook or None if not found
        """
        return self.playbooks.get(name)

    def list_playbooks(self) -> List[str]:
        """
        List all loaded playbooks.

        Returns:
            List of playbook names
        """
        return list(self.playbooks.keys())
