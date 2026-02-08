"""
Rules Engine Main Class

Central orchestrator for the custom alerting rules engine.
"""

import logging
from typing import Any, Dict, List, Optional
from pathlib import Path

from rules_engine.models import AlertRule, RuleEvaluationResult, ActionResult
from rules_engine.parser import RuleParser
from rules_engine.evaluator import RuleEvaluator
from rules_engine.actions import RuleActionExecutor, RuleCooldownManager


class RulesEngine:
    """
    Main rules engine orchestrator.

    Manages loading, evaluating, and executing custom alerting rules.
    """

    def __init__(
        self,
        rules_path: str = "rules",
        cooldown_db_path: str = "rules_cooldown.db",
        escalator=None,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize rules engine.

        Args:
            rules_path: Directory containing rule YAML files
            cooldown_db_path: Path to cooldown database
            escalator: Optional Escalator instance
            logger: Optional logger instance
        """
        self.rules_path = rules_path
        self.logger = logger or logging.getLogger(__name__)

        # Initialize components
        self.parser = RuleParser()
        self.evaluator = RuleEvaluator()
        self.action_executor = RuleActionExecutor(escalator=escalator, logger=self.logger)
        self.cooldown_manager = RuleCooldownManager(db_path=cooldown_db_path)

        # Load rules
        self.rules: List[AlertRule] = []
        self.rules_by_id: Dict[str, AlertRule] = {}
        self.load_rules()

    def load_rules(self):
        """Load all rules from the rules directory."""
        rules_dir = Path(self.rules_path)

        if not rules_dir.exists():
            self.logger.warning(f"Rules directory not found: {self.rules_path}")
            rules_dir.mkdir(parents=True, exist_ok=True)
            return

        try:
            self.rules = self.parser.parse_multiple_files(self.rules_path)
            self.rules_by_id = {rule.id: rule for rule in self.rules}
            self.logger.info(f"Loaded {len(self.rules)} rules from {self.rules_path}")

        except Exception as e:
            self.logger.error(f"Failed to load rules: {e}")
            self.rules = []
            self.rules_by_id = {}

    def reload_rules(self):
        """Reload rules from disk."""
        self.logger.info("Reloading rules...")
        self.load_rules()

    def evaluate_all(self, context: Dict[str, Any]) -> List[AlertRule]:
        """
        Evaluate all rules against the given context.

        Args:
            context: Current system context

        Returns:
            List of triggered rules
        """
        triggered_rules = []

        for rule in self.rules:
            # Skip disabled rules
            if not rule.enabled:
                continue

            # Evaluate rule
            result = self.evaluator.evaluate_rule(rule, context)

            # If matched and no errors
            if result.matched and not result.error:
                # Check cooldown and rate limits
                if self.cooldown_manager.can_trigger(
                    rule.id,
                    rule.cooldown_minutes,
                    rule.max_triggers_per_day
                ):
                    triggered_rules.append(rule)
                else:
                    self.logger.debug(
                        f"Rule {rule.id} matched but is in cooldown or rate limited"
                    )

        return triggered_rules

    def execute_triggered_rules(
        self,
        triggered_rules: List[AlertRule],
        context: Dict[str, Any]
    ) -> Dict[str, List[ActionResult]]:
        """
        Execute actions for all triggered rules.

        Args:
            triggered_rules: List of rules to execute
            context: Current context

        Returns:
            Dictionary mapping rule_id to list of action results
        """
        results = {}

        for rule in triggered_rules:
            self.logger.info(f"Executing actions for rule: {rule.id}")

            # Execute actions
            action_results = self.action_executor.execute_actions(
                rule.actions,
                context,
                rule.id
            )

            results[rule.id] = action_results

            # Record trigger
            self.cooldown_manager.record_trigger(rule.id, str(context.get('cycle_id', '')))

        return results

    def evaluate_and_execute(
        self,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Evaluate all rules and execute actions for triggered rules.

        Args:
            context: Current system context

        Returns:
            Summary of evaluation and execution
        """
        # Evaluate all rules
        triggered_rules = self.evaluate_all(context)

        if not triggered_rules:
            return {
                'triggered_count': 0,
                'triggered_rules': [],
                'action_results': {}
            }

        self.logger.info(f"{len(triggered_rules)} rule(s) triggered")

        # Execute actions
        action_results = self.execute_triggered_rules(triggered_rules, context)

        return {
            'triggered_count': len(triggered_rules),
            'triggered_rules': [rule.id for rule in triggered_rules],
            'action_results': action_results
        }

    def get_rule(self, rule_id: str) -> Optional[AlertRule]:
        """
        Get a rule by ID.

        Args:
            rule_id: Rule ID

        Returns:
            AlertRule or None if not found
        """
        return self.rules_by_id.get(rule_id)

    def add_rule(self, rule: AlertRule):
        """
        Add a new rule.

        Args:
            rule: Rule to add
        """
        # Validate rule
        validation = self.parser.validate_rule(rule)
        if not validation.valid:
            raise ValueError(f"Invalid rule: {validation.errors}")

        # Add to collections
        self.rules.append(rule)
        self.rules_by_id[rule.id] = rule

        self.logger.info(f"Added rule: {rule.id}")

    def remove_rule(self, rule_id: str):
        """
        Remove a rule.

        Args:
            rule_id: Rule ID to remove
        """
        if rule_id in self.rules_by_id:
            rule = self.rules_by_id[rule_id]
            self.rules.remove(rule)
            del self.rules_by_id[rule_id]
            self.logger.info(f"Removed rule: {rule_id}")

    def update_rule(self, rule: AlertRule):
        """
        Update an existing rule.

        Args:
            rule: Updated rule
        """
        # Validate rule
        validation = self.parser.validate_rule(rule)
        if not validation.valid:
            raise ValueError(f"Invalid rule: {validation.errors}")

        # Remove old version and add new
        self.remove_rule(rule.id)
        self.add_rule(rule)

        self.logger.info(f"Updated rule: {rule.id}")

    def list_rules(
        self,
        enabled_only: bool = False,
        tags: Optional[List[str]] = None
    ) -> List[AlertRule]:
        """
        List rules with optional filtering.

        Args:
            enabled_only: Only return enabled rules
            tags: Filter by tags

        Returns:
            List of rules
        """
        rules = self.rules

        if enabled_only:
            rules = [r for r in rules if r.enabled]

        if tags:
            rules = [r for r in rules if any(tag in r.tags for tag in tags)]

        return rules

    def get_rule_stats(self, rule_id: str) -> Dict[str, Any]:
        """
        Get statistics for a rule.

        Args:
            rule_id: Rule ID

        Returns:
            Statistics dictionary
        """
        rule = self.get_rule(rule_id)
        if not rule:
            raise ValueError(f"Rule not found: {rule_id}")

        stats = self.cooldown_manager.get_rule_stats(rule_id)
        stats['enabled'] = rule.enabled
        stats['priority'] = rule.priority.value

        # Get time until next trigger
        time_until_next = self.cooldown_manager.get_time_until_next_trigger(
            rule_id,
            rule.cooldown_minutes
        )
        if time_until_next:
            stats['cooldown_remaining_seconds'] = int(time_until_next.total_seconds())
        else:
            stats['cooldown_remaining_seconds'] = 0

        return stats

    def test_rule(
        self,
        rule_id: str,
        context: Dict[str, Any]
    ) -> RuleEvaluationResult:
        """
        Test a rule against a context without executing actions.

        Args:
            rule_id: Rule ID to test
            context: Test context

        Returns:
            Evaluation result
        """
        rule = self.get_rule(rule_id)
        if not rule:
            raise ValueError(f"Rule not found: {rule_id}")

        return self.evaluator.evaluate_rule(rule, context)

    def save_rule_to_file(self, rule_id: str, file_path: Optional[str] = None):
        """
        Save a rule to a YAML file.

        Args:
            rule_id: Rule ID
            file_path: Output file path (defaults to rules/{rule_id}.yaml)
        """
        rule = self.get_rule(rule_id)
        if not rule:
            raise ValueError(f"Rule not found: {rule_id}")

        if file_path is None:
            file_path = f"{self.rules_path}/{rule_id}.yaml"

        self.parser.save_rule_to_file(rule, file_path)
        self.logger.info(f"Saved rule {rule_id} to {file_path}")

    def get_summary(self) -> Dict[str, Any]:
        """
        Get summary of rules engine status.

        Returns:
            Summary dictionary
        """
        enabled_count = sum(1 for r in self.rules if r.enabled)
        disabled_count = len(self.rules) - enabled_count

        priority_counts = {}
        for priority in ['low', 'medium', 'high', 'critical']:
            count = sum(1 for r in self.rules if r.priority.value == priority)
            priority_counts[priority] = count

        return {
            'total_rules': len(self.rules),
            'enabled_rules': enabled_count,
            'disabled_rules': disabled_count,
            'priority_counts': priority_counts,
            'rules_path': self.rules_path
        }
