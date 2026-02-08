"""
Rule Parser

Parses rule definitions from YAML format.
"""

import yaml
from typing import Dict, Any, List
from pathlib import Path
from datetime import datetime

from rules_engine.models import (
    AlertRule,
    RuleConditions,
    Condition,
    RuleAction,
    RulePriority,
    ConditionOperator,
    ValidationResult
)


class RuleParser:
    """
    Parse rule definitions from YAML format.
    """

    def __init__(self):
        """Initialize the rule parser."""
        self.valid_operators = set(op.value for op in ConditionOperator)
        self.valid_priorities = set(p.value for p in RulePriority)

    def parse_yaml_file(self, file_path: str) -> AlertRule:
        """
        Parse rule from YAML file.

        Args:
            file_path: Path to YAML file

        Returns:
            Parsed AlertRule

        Raises:
            ValueError: If parsing fails
        """
        try:
            with open(file_path, 'r') as f:
                yaml_content = yaml.safe_load(f)

            if not yaml_content:
                raise ValueError(f"Empty YAML file: {file_path}")

            return self.parse_yaml_dict(yaml_content)

        except FileNotFoundError:
            raise ValueError(f"Rule file not found: {file_path}")
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML syntax: {e}")

    def parse_yaml_dict(self, yaml_data: Dict[str, Any]) -> AlertRule:
        """
        Parse rule from YAML dictionary.

        Args:
            yaml_data: YAML data as dictionary

        Returns:
            Parsed AlertRule
        """
        # Extract basic fields
        rule_id = yaml_data.get('id')
        if not rule_id:
            raise ValueError("Rule 'id' is required")

        name = yaml_data.get('name')
        if not name:
            raise ValueError("Rule 'name' is required")

        description = yaml_data.get('description', '')
        enabled = yaml_data.get('enabled', True)

        # Parse priority
        priority_str = yaml_data.get('priority', 'medium')
        if priority_str not in self.valid_priorities:
            raise ValueError(f"Invalid priority: {priority_str}")
        priority = RulePriority(priority_str)

        # Parse conditions
        conditions_data = yaml_data.get('conditions')
        if not conditions_data:
            raise ValueError("Rule 'conditions' are required")
        conditions = self._parse_conditions(conditions_data)

        # Parse actions
        actions_data = yaml_data.get('actions')
        if not actions_data:
            raise ValueError("Rule 'actions' are required")
        actions = self._parse_actions(actions_data)

        # Parse optional fields
        cooldown_minutes = yaml_data.get('cooldown_minutes', 60)
        max_triggers_per_day = yaml_data.get('max_triggers_per_day', 10)
        tags = yaml_data.get('tags', [])
        metadata = yaml_data.get('metadata', {})

        # Create rule
        rule = AlertRule(
            id=rule_id,
            name=name,
            description=description,
            enabled=enabled,
            priority=priority,
            conditions=conditions,
            actions=actions,
            cooldown_minutes=cooldown_minutes,
            max_triggers_per_day=max_triggers_per_day,
            tags=tags,
            metadata=metadata,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )

        return rule

    def _parse_conditions(self, conditions_data: Dict[str, Any]) -> RuleConditions:
        """Parse conditions from YAML data."""
        all_conditions = None
        any_conditions = None
        none_conditions = None

        if 'all' in conditions_data:
            all_conditions = [
                self._parse_condition(cond)
                for cond in conditions_data['all']
            ]

        if 'any' in conditions_data:
            any_conditions = [
                self._parse_condition(cond)
                for cond in conditions_data['any']
            ]

        if 'none' in conditions_data:
            none_conditions = [
                self._parse_condition(cond)
                for cond in conditions_data['none']
            ]

        if not all_conditions and not any_conditions and not none_conditions:
            raise ValueError("At least one condition group (all/any/none) must be provided")

        return RuleConditions(
            all=all_conditions,
            any=any_conditions,
            none=none_conditions
        )

    def _parse_condition(self, cond_data: Dict[str, Any]) -> Condition:
        """Parse a single condition."""
        field = cond_data.get('field')
        if not field:
            raise ValueError("Condition 'field' is required")

        operator_str = cond_data.get('operator')
        if not operator_str:
            raise ValueError("Condition 'operator' is required")

        if operator_str not in self.valid_operators:
            raise ValueError(f"Invalid operator: {operator_str}. Must be one of: {self.valid_operators}")

        operator = ConditionOperator(operator_str)

        if 'value' not in cond_data:
            raise ValueError("Condition 'value' is required")

        value = cond_data['value']

        return Condition(field=field, operator=operator, value=value)

    def _parse_actions(self, actions_data: List[Dict[str, Any]]) -> List[RuleAction]:
        """Parse actions from YAML data."""
        if not isinstance(actions_data, list):
            raise ValueError("Actions must be a list")

        actions = []
        for action_data in actions_data:
            action_type = action_data.get('type')
            if not action_type:
                raise ValueError("Action 'type' is required")

            params = action_data.get('params', {})

            actions.append(RuleAction(type=action_type, params=params))

        return actions

    def validate_rule(self, rule: AlertRule) -> ValidationResult:
        """
        Validate a rule.

        Args:
            rule: Rule to validate

        Returns:
            ValidationResult with any errors/warnings
        """
        errors = []
        warnings = []

        # Validate conditions
        if not rule.conditions.has_conditions():
            errors.append("Rule has no conditions defined")

        # Validate actions
        if not rule.actions or len(rule.actions) == 0:
            errors.append("Rule has no actions defined")

        # Validate cooldown
        if rule.cooldown_minutes < 0:
            errors.append("Cooldown minutes must be non-negative")

        if rule.cooldown_minutes == 0:
            warnings.append("Cooldown is 0 - rule may trigger very frequently")

        # Validate max triggers
        if rule.max_triggers_per_day <= 0:
            warnings.append("Max triggers per day is very low - rule may not trigger enough")

        if rule.max_triggers_per_day > 100:
            warnings.append("Max triggers per day is very high - may cause alert fatigue")

        # Check for empty fields
        if not rule.description:
            warnings.append("Rule has no description")

        if not rule.tags:
            warnings.append("Rule has no tags - consider adding for organization")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )

    def parse_multiple_files(self, directory: str) -> List[AlertRule]:
        """
        Parse all YAML rule files in a directory.

        Args:
            directory: Directory containing rule files

        Returns:
            List of parsed rules
        """
        rules = []
        rule_dir = Path(directory)

        if not rule_dir.exists():
            raise ValueError(f"Directory not found: {directory}")

        for yaml_file in rule_dir.glob('*.yaml'):
            try:
                rule = self.parse_yaml_file(str(yaml_file))
                rules.append(rule)
            except Exception as e:
                # Log error but continue parsing other files
                print(f"Warning: Failed to parse {yaml_file}: {e}")

        for yml_file in rule_dir.glob('*.yml'):
            try:
                rule = self.parse_yaml_file(str(yml_file))
                rules.append(rule)
            except Exception as e:
                print(f"Warning: Failed to parse {yml_file}: {e}")

        return rules

    def rule_to_yaml(self, rule: AlertRule) -> str:
        """
        Convert a rule to YAML string.

        Args:
            rule: Rule to convert

        Returns:
            YAML string
        """
        rule_dict = rule.to_dict()

        # Convert datetime to string if needed
        if rule_dict.get('created_at'):
            rule_dict.pop('created_at')
        if rule_dict.get('updated_at'):
            rule_dict.pop('updated_at')

        return yaml.dump(rule_dict, default_flow_style=False, sort_keys=False)

    def save_rule_to_file(self, rule: AlertRule, file_path: str):
        """
        Save a rule to YAML file.

        Args:
            rule: Rule to save
            file_path: Output file path
        """
        yaml_content = self.rule_to_yaml(rule)

        with open(file_path, 'w') as f:
            f.write(yaml_content)
