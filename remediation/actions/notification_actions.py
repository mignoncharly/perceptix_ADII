"""
Notification Actions - Send notifications to various channels
Handles Slack, email, and other notification systems.
"""
import logging
from typing import Dict, Any
from datetime import datetime

from remediation.actions.base import Action, ActionResult, ActionStatus


class SendSlackMessageAction(Action):
    """
    Send a message to Slack channel.
    """

    def __init__(self):
        super().__init__(
            name="send_slack_message",
            description="Send message to Slack channel"
        )

    def validate_params(self, params: Dict[str, Any]) -> bool:
        """Validate parameters."""
        required = ['channel', 'message']
        return all(key in params for key in required)

    def execute(self, params: Dict[str, Any]) -> ActionResult:
        """
        Send Slack message.

        Params:
            channel: Slack channel (e.g., "#data-ops")
            message: Message text
            username: Optional bot username
            icon_emoji: Optional emoji icon
        """
        try:
            channel = params['channel']
            message = params['message']
            username = params.get('username', 'Cognizant Bot')
            icon_emoji = params.get('icon_emoji', ':robot_face:')

            # In a real implementation, this would use Slack API
            self.logger.info(f"Slack message to {channel}: {message}")

            from config import load_config
            import requests

            config = load_config()
            webhook_url = config.notification.slack_webhook_url

            if not webhook_url:
                return ActionResult(
                    status=ActionStatus.SKIPPED,
                    message="Slack webhook URL not configured (skipped)",
                    action_name=self.name,
                    timestamp=datetime.now(),
                    details=params,
                    error="Configuration missing"
                )

            slack_payload = {
                'channel': channel,
                'username': username,
                'icon_emoji': icon_emoji,
                'text': message
            }

            response = requests.post(webhook_url, json=slack_payload, timeout=10)
            if response.status_code != 200:
                raise Exception(f"Slack returned {response.status_code}: {response.text}")

            return ActionResult(
                status=ActionStatus.SUCCESS,
                message=f"Slack message sent to {channel}",
                action_name=self.name,
                timestamp=datetime.now(),
                details={
                    "channel": channel,
                    "message_preview": message[:50] + "..." if len(message) > 50 else message
                },
                rollback_data={"channel": channel, "message": message}
            )

        except Exception as e:
            self.logger.error(f"Slack notification failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                message=f"Slack notification failed: {str(e)}",
                action_name=self.name,
                timestamp=datetime.now(),
                details=params,
                error=str(e)
            )

    def rollback(self, rollback_data: Dict[str, Any]) -> ActionResult:
        """
        Rollback not supported for notifications.
        """
        return ActionResult(
            status=ActionStatus.SKIPPED,
            message="Rollback not supported for notifications",
            action_name=self.name,
            timestamp=datetime.now(),
            details=rollback_data
        )


class SendEmailAction(Action):
    """
    Send an email notification.
    """

    def __init__(self):
        super().__init__(
            name="send_email",
            description="Send email notification"
        )

    def validate_params(self, params: Dict[str, Any]) -> bool:
        """Validate parameters."""
        # `to` can be inferred from config.notification.email_to if omitted.
        required = ['subject', 'body']
        return all(key in params for key in required)

    def execute(self, params: Dict[str, Any]) -> ActionResult:
        """
        Send email.

        Params:
            to: Email recipient(s) (string or list)
            subject: Email subject
            body: Email body
            from: Optional sender email
        """
        try:
            from config import load_config
            config = load_config()

            to_addr = params.get('to') or config.notification.email_to
            subject = params['subject']
            body = params['body']
            from_addr = params.get('from') or config.notification.email_from or 'perceptix@example.com'

            # Convert to list if string
            if isinstance(to_addr, str):
                to_addr = [to_addr]

            # In a real implementation, this would use SMTP or email service
            self.logger.info(f"Email to {to_addr}: {subject}")

            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            
            if not all([config.notification.email_smtp_host, config.notification.email_from, to_addr]):
                return ActionResult(
                    status=ActionStatus.SKIPPED,
                    message="Email configuration incomplete (skipped)",
                    action_name=self.name,
                    timestamp=datetime.now(),
                    details=params,
                    error="Configuration missing"
                )

            # Create message
            msg = MIMEMultipart()
            msg['Subject'] = subject
            msg['From'] = from_addr
            msg['To'] = ", ".join(to_addr)
            msg.attach(MIMEText(body, 'plain'))

            # Send email
            with smtplib.SMTP(config.notification.email_smtp_host, config.notification.email_smtp_port, timeout=10) as server:
                server.ehlo()
                if config.notification.email_use_tls and server.has_extn('STARTTLS'):
                    server.starttls()
                    server.ehlo()
                
                if config.notification.email_password:
                    server.login(config.notification.email_from, config.notification.email_password)
                
                server.send_message(msg)

            return ActionResult(
                status=ActionStatus.SUCCESS,
                message=f"Email sent to {', '.join(to_addr)}",
                action_name=self.name,
                timestamp=datetime.now(),
                details={
                    "to": to_addr,
                    "subject": subject
                },
                rollback_data={"to": to_addr, "subject": subject}
            )

        except Exception as e:
            self.logger.error(f"Email notification failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                message=f"Email notification failed: {str(e)}",
                action_name=self.name,
                timestamp=datetime.now(),
                details=params,
                error=str(e)
            )

    def rollback(self, rollback_data: Dict[str, Any]) -> ActionResult:
        """
        Rollback not supported for notifications.
        """
        return ActionResult(
            status=ActionStatus.SKIPPED,
            message="Rollback not supported for notifications",
            action_name=self.name,
            timestamp=datetime.now(),
            details=rollback_data
        )


class LogMessageAction(Action):
    """
    Log a message (simple action for testing/debugging).
    """

    def __init__(self):
        super().__init__(
            name="log_message",
            description="Log a message to system logs"
        )

    def validate_params(self, params: Dict[str, Any]) -> bool:
        """Validate parameters."""
        return 'message' in params

    def execute(self, params: Dict[str, Any]) -> ActionResult:
        """
        Log a message.

        Params:
            message: Message to log
            level: Log level (info, warning, error) - default: info
        """
        try:
            message = params['message']
            level = params.get('level', 'info').lower()

            # Log at appropriate level
            if level == 'warning':
                self.logger.warning(message)
            elif level == 'error':
                self.logger.error(message)
            else:
                self.logger.info(message)

            return ActionResult(
                status=ActionStatus.SUCCESS,
                message=f"Logged message at {level} level",
                action_name=self.name,
                timestamp=datetime.now(),
                details={"message": message, "level": level}
            )

        except Exception as e:
            return ActionResult(
                status=ActionStatus.FAILED,
                message=f"Log action failed: {str(e)}",
                action_name=self.name,
                timestamp=datetime.now(),
                details=params,
                error=str(e)
            )

    def rollback(self, rollback_data: Dict[str, Any]) -> ActionResult:
        """
        Rollback not supported for log actions.
        """
        return ActionResult(
            status=ActionStatus.SKIPPED,
            message="Rollback not supported for log actions",
            action_name=self.name,
            timestamp=datetime.now(),
            details=rollback_data
        )


# Register actions
from remediation.actions.base import get_global_registry

registry = get_global_registry()
registry.register('send_slack_message', SendSlackMessageAction)
registry.register('send_email', SendEmailAction)
registry.register('log_message', LogMessageAction)
