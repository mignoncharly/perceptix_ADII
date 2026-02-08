"""
Perceptix Slack Bot

Interactive Slack bot for incident management.
Supports both real Slack integration and mock mode for testing.
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

from slack_bot.formatters.message_formatter import MessageFormatter
from slack_bot.incident_acknowledger import IncidentAcknowledger


logger = logging.getLogger("PerceptixSlackBot")


class MockSlackClient:
    """Mock Slack client for testing without real Slack."""

    def __init__(self):
        self.messages = []
        self.threads = {}

    def chat_postMessage(self, **kwargs):
        """Mock post message."""
        message_id = f"msg_{len(self.messages)}"
        message = {
            'ts': message_id,
            'channel': kwargs.get('channel', '#general'),
            'text': kwargs.get('text', ''),
            'blocks': kwargs.get('blocks', []),
            'thread_ts': kwargs.get('thread_ts')
        }
        self.messages.append(message)

        logger.info(f"[MOCK] Posted to {message['channel']}: {message['text'][:50]}")

        return {
            'ok': True,
            'ts': message_id,
            'channel': kwargs.get('channel')
        }

    def chat_update(self, **kwargs):
        """Mock update message."""
        logger.info(f"[MOCK] Updated message: {kwargs.get('text', '')[:50]}")
        return {'ok': True}

    def get_messages(self):
        """Get all posted messages."""
        return self.messages

    def clear_messages(self):
        """Clear message history."""
        self.messages = []


class PerceptixSlackBot:
    """
    Interactive Slack bot for Perceptix system.

    Supports:
    - Slash commands for status, incidents, acknowledgment
    - Interactive buttons for incident management
    - Scheduled summaries
    - Incident threading
    - Mock mode for testing
    """

    def __init__(self, config, system=None):
        """
        Initialize Slack bot.

        Args:
            config: SlackBotConfig instance
            system: Optional PerceptixSystem instance
        """
        self.config = config
        self.system = system
        self.formatter = MessageFormatter()
        self.acknowledger = IncidentAcknowledger()

        # Use mock client if in mock mode or no token
        if config.mock_mode or not config.bot_token:
            logger.info("Initializing in MOCK mode")
            self.client = MockSlackClient()
            self.mock_mode = True
        else:
            logger.info("Initializing with real Slack client")
            try:
                from slack_sdk import WebClient
                self.client = WebClient(token=config.bot_token)
                self.mock_mode = False
            except ImportError:
                logger.warning("slack_sdk not available, using mock mode")
                self.client = MockSlackClient()
                self.mock_mode = True

        self.default_channel = config.default_channel
        self.enable_threading = config.enable_threading
        self.enable_buttons = config.enable_buttons

        logger.info(f"Slack bot initialized (mock={self.mock_mode})")

    def post_incident(
        self,
        incident: Dict[str, Any],
        channel: Optional[str] = None
    ) -> Optional[str]:
        """
        Post an incident notification to Slack.

        Args:
            incident: Incident report dictionary
            channel: Optional channel (uses default if not specified)

        Returns:
            Message timestamp (thread ID) if successful
        """
        try:
            channel = channel or self.default_channel
            message = self.formatter.format_incident(
                incident,
                include_buttons=self.enable_buttons
            )

            response = self.client.chat_postMessage(
                channel=channel,
                text=message['text'],
                blocks=message['blocks']
            )

            thread_ts = response.get('ts')
            logger.info(f"Posted incident {incident.get('report_id')[:8]} to {channel}")

            return thread_ts

        except Exception as e:
            logger.error(f"Failed to post incident: {e}")
            return None

    def post_status(self, metrics: Dict[str, Any], channel: Optional[str] = None) -> bool:
        """
        Post system status to Slack.

        Args:
            metrics: System metrics dictionary
            channel: Optional channel

        Returns:
            True if successful
        """
        try:
            channel = channel or self.default_channel
            message = self.formatter.format_status(metrics)

            self.client.chat_postMessage(
                channel=channel,
                text=message['text'],
                blocks=message['blocks']
            )

            logger.info(f"Posted status to {channel}")
            return True

        except Exception as e:
            logger.error(f"Failed to post status: {e}")
            return False

    def post_incident_list(
        self,
        incidents: List[Dict[str, Any]],
        channel: Optional[str] = None,
        limit: int = 10
    ) -> bool:
        """
        Post list of incidents to Slack.

        Args:
            incidents: List of incident dictionaries
            channel: Optional channel
            limit: Maximum number to show

        Returns:
            True if successful
        """
        try:
            channel = channel or self.default_channel
            message = self.formatter.format_incident_list(incidents, limit)

            self.client.chat_postMessage(
                channel=channel,
                text=message['text'],
                blocks=message['blocks']
            )

            logger.info(f"Posted incident list ({len(incidents)}) to {channel}")
            return True

        except Exception as e:
            logger.error(f"Failed to post incident list: {e}")
            return False

    def acknowledge_incident(
        self,
        incident_id: str,
        user_id: str,
        user_name: Optional[str] = None,
        channel: Optional[str] = None
    ) -> bool:
        """
        Acknowledge an incident.

        Args:
            incident_id: Incident report ID
            user_id: User ID who acknowledged
            user_name: Optional user display name
            channel: Optional channel to post confirmation

        Returns:
            True if successful
        """
        try:
            # Record acknowledgment
            success = self.acknowledger.acknowledge(
                incident_id,
                user_id,
                user_name
            )

            if not success:
                logger.warning(f"Incident {incident_id} already acknowledged by {user_id}")
                return False

            # Post confirmation
            if channel:
                message = self.formatter.format_acknowledgment(incident_id, user_id)
                self.client.chat_postMessage(
                    channel=channel,
                    text=message['text'],
                    blocks=message['blocks']
                )

            logger.info(f"Incident {incident_id} acknowledged by {user_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to acknowledge incident: {e}")
            return False

    def post_daily_summary(
        self,
        incidents: List[Dict[str, Any]],
        date: Optional[str] = None,
        channel: Optional[str] = None
    ) -> bool:
        """
        Post daily incident summary.

        Args:
            incidents: List of incidents from the day
            date: Optional date string
            channel: Optional channel

        Returns:
            True if successful
        """
        try:
            if date is None:
                date = datetime.now().strftime('%Y-%m-%d')

            channel = channel or self.default_channel
            message = self.formatter.format_daily_summary(incidents, date)

            self.client.chat_postMessage(
                channel=channel,
                text=message['text'],
                blocks=message['blocks']
            )

            logger.info(f"Posted daily summary for {date} to {channel}")
            return True

        except Exception as e:
            logger.error(f"Failed to post daily summary: {e}")
            return False

    def post_to_thread(
        self,
        thread_ts: str,
        text: str,
        channel: Optional[str] = None
    ) -> bool:
        """
        Post a message to an incident thread.

        Args:
            thread_ts: Thread timestamp (message ID)
            text: Message text
            channel: Optional channel

        Returns:
            True if successful
        """
        try:
            channel = channel or self.default_channel

            self.client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text=text
            )

            logger.info(f"Posted to thread {thread_ts}")
            return True

        except Exception as e:
            logger.error(f"Failed to post to thread: {e}")
            return False

    def handle_command(self, command: str, args: List[str]) -> Dict[str, Any]:
        """
        Handle a slash command.

        Args:
            command: Command name (status, incidents, ack, help)
            args: Command arguments

        Returns:
            Response message
        """
        if command == 'status':
            return self._handle_status_command()

        elif command == 'incidents':
            limit = int(args[0]) if args and args[0].isdigit() else 10
            return self._handle_incidents_command(limit)

        elif command == 'ack':
            if not args:
                return self.formatter.format_error("Usage: /perceptix ack <incident_id>")
            return self._handle_ack_command(args[0])

        elif command == 'help':
            return self.formatter.format_help()

        else:
            return self.formatter.format_error(f"Unknown command: {command}")

    def _handle_status_command(self) -> Dict[str, Any]:
        """Handle status command."""
        if not self.system:
            return self.formatter.format_error("System not initialized")

        try:
            metrics = self.system.get_metrics_summary()
            return self.formatter.format_status(metrics)
        except Exception as e:
            return self.formatter.format_error(f"Failed to get status: {e}")

    def _handle_incidents_command(self, limit: int = 10) -> Dict[str, Any]:
        """Handle incidents command."""
        if not self.system:
            return self.formatter.format_error("System not initialized")

        try:
            incidents = self.system.historian.get_recent_incidents(limit=limit)
            return self.formatter.format_incident_list(incidents, limit)
        except Exception as e:
            return self.formatter.format_error(f"Failed to get incidents: {e}")

    def _handle_ack_command(self, incident_id: str) -> Dict[str, Any]:
        """Handle acknowledgment command."""
        try:
            # Record acknowledgment (user_id would come from Slack context in real usage)
            success = self.acknowledger.acknowledge(
                incident_id,
                user_id="cli_user",
                user_name="CLI User"
            )

            if success:
                return self.formatter.format_acknowledgment(incident_id, "cli_user")
            else:
                return self.formatter.format_error(
                    f"Incident {incident_id} already acknowledged or not found"
                )

        except Exception as e:
            return self.formatter.format_error(f"Failed to acknowledge: {e}")

    def get_mock_messages(self) -> List[Dict[str, Any]]:
        """
        Get all mock messages (for testing).

        Returns:
            List of posted messages
        """
        if isinstance(self.client, MockSlackClient):
            return self.client.get_messages()
        return []

    def clear_mock_messages(self):
        """Clear mock message history (for testing)."""
        if isinstance(self.client, MockSlackClient):
            self.client.clear_messages()
