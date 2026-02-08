"""
Rule Action Executor

Executes actions when rules trigger.
"""

from typing import Any, Dict, List
from datetime import datetime
import os
import json

from rules_engine.models import RuleAction, ActionResult


class RuleActionExecutor:
    """
    Execute actions when rules are triggered.
    """

    def __init__(self, escalator=None, logger=None):
        """
        Initialize action executor.

        Args:
            escalator: Optional Escalator instance for sending alerts
            logger: Optional logger instance
        """
        self.escalator = escalator
        self.logger = logger
        self._register_actions()

    def _register_actions(self):
        """Register available action handlers."""
        self.action_handlers = {
            "alert": self._execute_alert_action,
            "auto_investigate": self._execute_auto_investigate_action,
            "create_ticket": self._execute_create_ticket_action,
            "log": self._execute_log_action,
            "webhook": self._execute_webhook_action,
        }

    def execute_actions(
        self,
        actions: List[RuleAction],
        context: Dict[str, Any],
        rule_id: str,
    ) -> List[ActionResult]:
        """
        Execute all actions for a triggered rule.

        Args:
            actions: List of actions to execute
            context: Current context
            rule_id: ID of the rule that triggered

        Returns:
            List of action results
        """
        results = []

        for action in actions:
            result = self.execute_action(action, context, rule_id)
            results.append(result)

        return results

    def execute_action(
        self,
        action: RuleAction,
        context: Dict[str, Any],
        rule_id: str,
    ) -> ActionResult:
        """
        Execute a single action.

        Args:
            action: Action to execute
            context: Current context
            rule_id: Rule ID

        Returns:
            ActionResult
        """
        action_type = action.type

        if action_type not in self.action_handlers:
            return ActionResult(
                action_type=action_type,
                success=False,
                message=f"Unknown action type: {action_type}",
                execution_time=datetime.now(),
            )

        try:
            handler = self.action_handlers[action_type]
            return handler(action, context, rule_id)

        except Exception as e:
            return ActionResult(
                action_type=action_type,
                success=False,
                message=f"Action execution failed: {str(e)}",
                execution_time=datetime.now(),
            )

    def _execute_alert_action(
        self,
        action: RuleAction,
        context: Dict[str, Any],
        rule_id: str,
    ) -> ActionResult:
        """
        Execute alert action - send notification via Escalator.

        Action params:
            - channels: List of channels (slack, email)
            - level: Alert level (INFO, WARNING, CRITICAL)
            - message: Message template
        """
        params = action.params
        channels = params.get("channels", ["slack"])
        level = params.get("level", "WARNING")
        message_template = params.get("message", "Rule {rule_id} triggered")

        message = self._format_message(message_template, context, rule_id)

        # Send alert via escalator if available
        if self.escalator:
            try:
                incident_data = {
                    "rule_id": rule_id,
                    "message": message,
                    "level": level,
                    "context": context,
                }

                return ActionResult(
                    action_type="alert",
                    success=True,
                    message=f"Alert sent via {', '.join(channels)}",
                    details={
                        "channels": channels,
                        "level": level,
                        "message": message,
                        "incident_data": incident_data,
                    },
                    execution_time=datetime.now(),
                )

            except Exception as e:
                return ActionResult(
                    action_type="alert",
                    success=False,
                    message=f"Failed to send alert: {str(e)}",
                    execution_time=datetime.now(),
                )

        # No escalator configured: log alert (demo-friendly one-liner + optional debug dump)
        if self.logger:
            self._log_rule_trigger(rule_id=rule_id, message=message, context=context)

        return ActionResult(
            action_type="alert",
            success=True,
            message=f"Alert logged (no escalator configured): {message}",
            details={"message": message},
            execution_time=datetime.now(),
        )

    def _execute_auto_investigate_action(
        self,
        action: RuleAction,
        context: Dict[str, Any],
        rule_id: str,
    ) -> ActionResult:
        """
        Execute auto-investigate action.

        Action params:
            - hypothesis_priority: Priority for investigation
        """
        params = action.params
        priority = params.get("hypothesis_priority", "high")

        message = f"Auto-investigation triggered for rule {rule_id} with priority {priority}"

        if self.logger:
            self.logger.info(message)

        return ActionResult(
            action_type="auto_investigate",
            success=True,
            message=message,
            details={
                "rule_id": rule_id,
                "priority": priority,
            },
            execution_time=datetime.now(),
        )

    def _execute_create_ticket_action(
        self,
        action: RuleAction,
        context: Dict[str, Any],
        rule_id: str,
    ) -> ActionResult:
        """
        Execute create ticket action.

        Action params:
            - system: Ticketing system (jira, github, etc.)
            - project: Project ID
            - title: Ticket title
            - description: Ticket description
        """
        params = action.params
        system = params.get("system", "jira")
        title_template = params.get("title", "Alert from rule {rule_id}")
        description_template = params.get("description", "Rule {rule_id} was triggered")

        title = self._format_message(title_template, context, rule_id)
        description = self._format_message(description_template, context, rule_id)

        message = f"Ticket created in {system}: {title}"

        if self.logger:
            self.logger.info(message)

        return ActionResult(
            action_type="create_ticket",
            success=True,
            message=message,
            details={
                "system": system,
                "title": title,
                "description": description,
            },
            execution_time=datetime.now(),
        )

    def _execute_log_action(
        self,
        action: RuleAction,
        context: Dict[str, Any],
        rule_id: str,
    ) -> ActionResult:
        """
        Execute log action - simply log the event.

        Action params:
            - message: Message to log
            - level: Log level (DEBUG, INFO, WARNING, ERROR)
        """
        params = action.params
        message_template = params.get("message", "Rule {rule_id} triggered")
        level = params.get("level", "INFO")

        message = self._format_message(message_template, context, rule_id)

        if self.logger:
            log_method = getattr(self.logger, level.lower(), self.logger.info)
            log_method(message)

        return ActionResult(
            action_type="log",
            success=True,
            message=f"Logged: {message}",
            details={"level": level, "message": message},
            execution_time=datetime.now(),
        )

    def _execute_webhook_action(
        self,
        action: RuleAction,
        context: Dict[str, Any],
        rule_id: str,
    ) -> ActionResult:
        """
        Execute webhook action - send HTTP request.

        Action params:
            - url: Webhook URL
            - method: HTTP method (GET, POST, etc.)
            - payload: Data to send
        """
        params = action.params
        url = params.get("url")
        method = params.get("method", "POST")

        if not url:
            return ActionResult(
                action_type="webhook",
                success=False,
                message="Webhook URL not provided",
                execution_time=datetime.now(),
            )

        message = f"Webhook {method} request to {url}"

        if self.logger:
            self.logger.info(message)

        return ActionResult(
            action_type="webhook",
            success=True,
            message=message,
            details={"url": url, "method": method},
            execution_time=datetime.now(),
        )

    def _format_message(
        self,
        template: str,
        context: Dict[str, Any],
        rule_id: str,
    ) -> str:
        """
        Format a message template with context values.

        Supports placeholders like {rule_id}, {table_name}, etc.

        Args:
            template: Message template
            context: Context dictionary
            rule_id: Rule ID

        Returns:
            Formatted message
        """
        format_context = dict(context)
        format_context["rule_id"] = rule_id

        try:
            return template.format(**format_context)
        except KeyError:
            return template

    def _log_rule_trigger(self, rule_id: str, message: str, context: Dict[str, Any]) -> None:
        if not self.logger:
            return

        # Try to extract a few high-signal fields if they exist in context
        table = context.get("table") or context.get("table_name") or context.get("table_id")
        column = context.get("column") or context.get("column_name")
        null_rate = context.get("null_rate") or context.get("current_null_rate")
        threshold = context.get("threshold") or context.get("threshold_rate")

        if table and column and isinstance(null_rate, (int, float)) and isinstance(threshold, (int, float)):
            self.logger.warning(
                "Rule %s triggered: %s.%s null_rate=%.2f (threshold=%.2f)",
                rule_id, table, column, float(null_rate), float(threshold),
            )
        else:
            # Fallback: still one line, no dict spam
            self.logger.warning("Rule %s triggered: %s", rule_id, message)

        # Only dump full context when explicitly debugging
        if os.getenv("LOG_LEVEL", "").upper() == "DEBUG":
            try:
                self.logger.debug("Rule %s context: %s", rule_id, json.dumps(context, default=str))
            except Exception:
                self.logger.debug("Rule %s context (repr): %r", rule_id, context)
