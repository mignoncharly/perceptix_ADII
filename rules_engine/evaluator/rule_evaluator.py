"""
Rule Evaluator

Evaluates rules against system state and context.
"""

import re
from typing import Any, Dict, List
from datetime import datetime

from rules_engine.models import (
    AlertRule,
    RuleConditions,
    Condition,
    ConditionOperator,
    RuleEvaluationResult
)


class RuleEvaluator:
    """
    Evaluate rules against system context.
    """

    def __init__(self):
        """Initialize the rule evaluator."""
        pass

    def evaluate_rule(
        self,
        rule: AlertRule,
        context: Dict[str, Any]
    ) -> RuleEvaluationResult:
        """
        Evaluate a rule against the current context.

        Args:
            rule: Rule to evaluate
            context: Current system context (metrics, incidents, etc.)

        Returns:
            RuleEvaluationResult
        """
        try:
            # Evaluate conditions
            matched = self._evaluate_conditions_group(rule.conditions, context)

            # Build detailed results
            conditions_met = {}
            if rule.conditions.all:
                conditions_met['all'] = all(
                    self._evaluate_condition(cond, context)
                    for cond in rule.conditions.all
                )
            if rule.conditions.any:
                conditions_met['any'] = any(
                    self._evaluate_condition(cond, context)
                    for cond in rule.conditions.any
                )
            if rule.conditions.none:
                conditions_met['none'] = not any(
                    self._evaluate_condition(cond, context)
                    for cond in rule.conditions.none
                )

            return RuleEvaluationResult(
                rule_id=rule.id,
                matched=matched,
                conditions_met=conditions_met,
                evaluation_time=datetime.now(),
                context_snapshot=self._create_context_snapshot(context)
            )

        except Exception as e:
            return RuleEvaluationResult(
                rule_id=rule.id,
                matched=False,
                conditions_met={},
                evaluation_time=datetime.now(),
                context_snapshot={},
                error=str(e)
            )

    def _evaluate_conditions_group(
        self,
        conditions: RuleConditions,
        context: Dict[str, Any]
    ) -> bool:
        """
        Evaluate a group of conditions with AND/OR/NOT logic.

        Args:
            conditions: Conditions to evaluate
            context: Context dictionary

        Returns:
            True if conditions match, False otherwise
        """
        results = []

        # Evaluate ALL (AND) conditions
        if conditions.all:
            all_match = all(
                self._evaluate_condition(cond, context)
                for cond in conditions.all
            )
            results.append(all_match)

        # Evaluate ANY (OR) conditions
        if conditions.any:
            any_match = any(
                self._evaluate_condition(cond, context)
                for cond in conditions.any
            )
            results.append(any_match)

        # Evaluate NONE (NOT) conditions
        if conditions.none:
            none_match = not any(
                self._evaluate_condition(cond, context)
                for cond in conditions.none
            )
            results.append(none_match)

        # All condition groups must pass
        return all(results) if results else False

    def _evaluate_condition(
        self,
        condition: Condition,
        context: Dict[str, Any]
    ) -> bool:
        """
        Evaluate a single condition.

        Args:
            condition: Condition to evaluate
            context: Context dictionary

        Returns:
            True if condition matches, False otherwise
        """
        # Resolve field value from context
        field_value = self._resolve_field_path(condition.field, context)

        # If field doesn't exist, condition fails
        if field_value is None:
            return False

        # Evaluate based on operator
        operator = condition.operator
        expected_value = condition.value

        if operator == ConditionOperator.EQUALS:
            return field_value == expected_value

        elif operator == ConditionOperator.NOT_EQUALS:
            return field_value != expected_value

        elif operator == ConditionOperator.GREATER_THAN:
            return self._compare_numeric(field_value, expected_value, '>')

        elif operator == ConditionOperator.GREATER_THAN_OR_EQUAL:
            return self._compare_numeric(field_value, expected_value, '>=')

        elif operator == ConditionOperator.LESS_THAN:
            return self._compare_numeric(field_value, expected_value, '<')

        elif operator == ConditionOperator.LESS_THAN_OR_EQUAL:
            return self._compare_numeric(field_value, expected_value, '<=')

        elif operator == ConditionOperator.CONTAINS:
            return self._check_contains(field_value, expected_value)

        elif operator == ConditionOperator.NOT_CONTAINS:
            return not self._check_contains(field_value, expected_value)

        elif operator == ConditionOperator.IN:
            return field_value in expected_value if isinstance(expected_value, (list, tuple, set)) else False

        elif operator == ConditionOperator.NOT_IN:
            return field_value not in expected_value if isinstance(expected_value, (list, tuple, set)) else False

        elif operator == ConditionOperator.REGEX:
            return bool(re.search(expected_value, str(field_value)))

        elif operator == ConditionOperator.STARTS_WITH:
            return str(field_value).startswith(str(expected_value))

        elif operator == ConditionOperator.ENDS_WITH:
            return str(field_value).endswith(str(expected_value))

        else:
            return False

    def _resolve_field_path(
        self,
        field_path: str,
        context: Dict[str, Any]
    ) -> Any:
        """
        Resolve a field path from context.

        Supports nested paths like 'null_rates.attribution_source'

        Args:
            field_path: Field path (e.g., 'table_name' or 'null_rates.column')
            context: Context dictionary

        Returns:
            Field value or None if not found
        """
        # Split path by dots
        parts = field_path.split('.')

        current = context
        for part in parts:
            if isinstance(current, dict):
                if part in current:
                    current = current[part]
                else:
                    return None
            else:
                # Can't navigate further
                return None

        return current

    def _compare_numeric(self, field_value: Any, expected: Any, operator: str) -> bool:
        """
        Compare numeric values.

        Args:
            field_value: Actual value
            expected: Expected value
            operator: Comparison operator (>, >=, <, <=)

        Returns:
            Comparison result
        """
        try:
            # Convert to float for comparison
            field_val = float(field_value)
            expected_val = float(expected)

            if operator == '>':
                return field_val > expected_val
            elif operator == '>=':
                return field_val >= expected_val
            elif operator == '<':
                return field_val < expected_val
            elif operator == '<=':
                return field_val <= expected_val
            else:
                return False

        except (ValueError, TypeError):
            # If not numeric, comparison fails
            return False

    def _check_contains(self, field_value: Any, expected: Any) -> bool:
        """
        Check if field_value contains expected.

        Works for strings, lists, etc.

        Args:
            field_value: Value to search in
            expected: Value to search for

        Returns:
            True if contains, False otherwise
        """
        if isinstance(field_value, str):
            return str(expected) in field_value
        elif isinstance(field_value, (list, tuple, set)):
            return expected in field_value
        elif isinstance(field_value, dict):
            return expected in field_value.keys() or expected in field_value.values()
        else:
            return False

    def _create_context_snapshot(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a lightweight snapshot of the context for logging.

        Args:
            context: Full context

        Returns:
            Snapshot with key fields only
        """
        snapshot = {}

        # Include key fields if present
        key_fields = [
            'table_name',
            'confidence',
            'incident_type',
            'null_rates',
            'row_count',
            'cycle_id'
        ]

        for field in key_fields:
            if field in context:
                snapshot[field] = context[field]

        return snapshot

    def evaluate_multiple_rules(
        self,
        rules: List[AlertRule],
        context: Dict[str, Any]
    ) -> List[RuleEvaluationResult]:
        """
        Evaluate multiple rules against context.

        Args:
            rules: List of rules to evaluate
            context: Context dictionary

        Returns:
            List of evaluation results
        """
        results = []

        for rule in rules:
            # Skip disabled rules
            if not rule.enabled:
                continue

            result = self.evaluate_rule(rule, context)
            results.append(result)

        return results

    def get_matching_rules(
        self,
        rules: List[AlertRule],
        context: Dict[str, Any]
    ) -> List[AlertRule]:
        """
        Get all rules that match the given context.

        Args:
            rules: List of rules to check
            context: Context dictionary

        Returns:
            List of matching rules
        """
        matching_rules = []

        for rule in rules:
            if not rule.enabled:
                continue

            result = self.evaluate_rule(rule, context)
            if result.matched and not result.error:
                matching_rules.append(rule)

        return matching_rules
