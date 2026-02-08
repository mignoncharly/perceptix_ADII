"""
Escalator Module: Multi-Channel Alert Notification System
Handles incident notifications via multiple channels with proper error handling.
"""
import logging
from typing import Dict, Any, List
from datetime import datetime

from models import IncidentReport, Criticality
from exceptions import EscalatorError, NotificationError, AlertRoutingError
from config import PerceptixConfig
from resilience import exponential_backoff


logger = logging.getLogger("PerceptixEscalator")


class NotificationChannel:
    """Base class for notification channels."""

    def __init__(self, config: PerceptixConfig):
        self.config = config
        self.enabled = False

    def send(self, report: IncidentReport, message: str, alert_level: str) -> bool:
        """
        Send notification through this channel.

        Args:
            report: Incident report
            message: Formatted message
            alert_level: Alert level

        Returns:
            bool: True if sent successfully

        Raises:
            NotificationError: If sending fails
        """
        raise NotImplementedError


class ConsoleChannel(NotificationChannel):
    """Console output channel."""

    def __init__(self, config: PerceptixConfig):
        super().__init__(config)
        self.enabled = "console" in config.notification.channels

    def send(self, report: IncidentReport, message: str, alert_level: str) -> bool:
        """Send to console."""
        if not self.enabled:
            return False

        try:
            # Color codes for different alert levels
            colors = {
                "CRITICAL": "\033[91m",  # Red
                "WARNING": "\033[93m",   # Yellow
                "INFO": "\033[94m",      # Blue
                "RESET": "\033[0m"
            }

            color = colors.get(alert_level, colors["INFO"])
            reset = colors["RESET"]

            print(f"\n{color}{message}{reset}\n")
            return True

        except Exception as e:
            raise NotificationError(
                f"Console notification failed: {e}",
                component="ConsoleChannel"
            )


class SlackChannel(NotificationChannel):
    """Slack webhook channel."""

    def __init__(self, config: PerceptixConfig):
        super().__init__(config)
        self.webhook_url = config.notification.slack_webhook_url
        self.enabled = "slack" in config.notification.channels and self.webhook_url

    @exponential_backoff(max_retries=2, base_delay=1.0)
    def send(self, report: IncidentReport, message: str, alert_level: str) -> bool:
        """Send to Slack via webhook."""
        if not self.enabled:
            return False

        try:
            import requests

            # Format for Slack
            color_map = {
                "CRITICAL": "danger",
                "WARNING": "warning",
                "INFO": "good"
            }

            payload = {
                "attachments": [{
                    "color": color_map.get(alert_level, "good"),
                    "title": f"🚨 {report.incident_type.value}",
                    "text": report.root_cause_analysis,
                    "fields": [
                        {
                            "title": "Status",
                            "value": report.verification_status.value,
                            "short": True
                        },
                        {
                            "title": "Confidence",
                            "value": f"{report.final_confidence_score}%",
                            "short": True
                        },
                        {
                            "title": "Report ID",
                            "value": report.report_id,
                            "short": False
                        }
                    ],
                    "footer": "Perceptix Autonomous Agent",
                    "ts": int(datetime.now().timestamp())
                }]
            }

            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=10
            )

            if response.status_code != 200:
                raise NotificationError(
                    f"Slack webhook returned {response.status_code}",
                    component="SlackChannel"
                )

            logger.info(f"[SLACK] Notification sent: {report.report_id}")
            return True

        except ImportError:
            logger.warning("[SLACK] requests library not available")
            return False

        except Exception as e:
            raise NotificationError(
                f"Slack notification failed: {e}",
                component="SlackChannel",
                context={"report_id": report.report_id}
            )


class EmailChannel(NotificationChannel):
    """Email notification channel via SMTP."""

    def __init__(self, config: PerceptixConfig):
        super().__init__(config)
        self.smtp_host = config.notification.email_smtp_host
        self.smtp_port = config.notification.email_smtp_port
        self.from_address = config.notification.email_from
        self.to_addresses = config.notification.email_to
        self.enabled = (
            "email" in config.notification.channels and
            self.smtp_host and
            self.from_address and
            self.to_addresses
        )

    @exponential_backoff(max_retries=2, base_delay=1.0)
    def send(self, report: IncidentReport, message: str, alert_level: str) -> bool:
        """Send email notification via SMTP."""
        if not self.enabled:
            return False

        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"[{alert_level}] Perceptix Alert: {report.incident_type.value}"
            msg['From'] = self.from_address
            msg['To'] = self.to_addresses

            # Plain text version
            text_content = message

            # HTML version
            html_content = self._format_html_email(report, alert_level)

            # Attach both versions
            part1 = MIMEText(text_content, 'plain')
            part2 = MIMEText(html_content, 'html')
            msg.attach(part1)
            msg.attach(part2)

            # Send email
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10) as server:
                server.ehlo()
                if self.config.notification.email_use_tls and server.has_extn('STARTTLS'):
                    server.starttls()
                    server.ehlo()

                if self.config.notification.email_password:
                    server.login(self.from_address, self.config.notification.email_password)

                server.send_message(msg)

            logger.info(f"[EMAIL] Notification sent for {report.report_id}")
            return True

        except ImportError:
            logger.warning("[EMAIL] smtplib not available")
            return False

        except Exception as e:
            raise NotificationError(
                f"Email notification failed: {e}",
                component="EmailChannel",
                context={"report_id": report.report_id}
            )

    def _format_html_email(self, report: IncidentReport, alert_level: str) -> str:
        """Format email as HTML with styling."""
        color_map = {
            "CRITICAL": "#dc3545",  # Red
            "WARNING": "#ffc107",   # Yellow
            "INFO": "#17a2b8"       # Blue
        }

        color = color_map.get(alert_level, "#6c757d")

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background-color: {color}; color: white; padding: 20px; border-radius: 5px 5px 0 0; }}
        .content {{ background-color: #f8f9fa; padding: 20px; border: 1px solid #dee2e6; }}
        .footer {{ background-color: #f8f9fa; padding: 10px; text-align: center; border-radius: 0 0 5px 5px; }}
        .label {{ font-weight: bold; color: #495057; }}
        .value {{ color: #212529; }}
        .evidence {{ background-color: white; padding: 10px; margin: 10px 0; border-left: 3px solid {color}; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2>🚨 Perceptix Alert: {report.incident_type.value}</h2>
        </div>
        <div class="content">
            <p><span class="label">Report ID:</span> <span class="value">{report.report_id}</span></p>
            <p><span class="label">Timestamp:</span> <span class="value">{report.timestamp}</span></p>
            <p><span class="label">Status:</span> <span class="value">{report.verification_status.value}</span></p>
            <p><span class="label">Confidence:</span> <span class="value">{report.final_confidence_score}%</span></p>

            <h3>Root Cause Analysis</h3>
            <p>{report.root_cause_analysis}</p>

            <h3>Evidence</h3>
            {"".join(f'<div class="evidence">• {evidence}</div>' for evidence in report.evidence_summary)}
        </div>
        <div class="footer">
            <p>Generated by Perceptix Autonomous Agent</p>
        </div>
    </div>
</body>
</html>
        """
        return html


class Escalator:
    """
    Multi-Channel Notification System.
    Routes alerts to appropriate channels based on severity and configuration.
    """

    def __init__(self, config: PerceptixConfig):
        """
        Initialize Escalator with configuration.

        Args:
            config: System configuration
        """
        self.config = config
        self.component_id = "ESCALATOR_V2"

        # Initialize channels
        self.channels: List[NotificationChannel] = [
            ConsoleChannel(config),
            SlackChannel(config),
            EmailChannel(config)
        ]

        # Initialize Slack bot if enabled
        self.slack_bot = None
        if config.slack_bot.enabled:
            try:
                from slack_bot import PerceptixSlackBot
                self.slack_bot = PerceptixSlackBot(config.slack_bot)
                logger.info("[ESCALATOR] Slack bot enabled")
            except ImportError:
                logger.warning("[ESCALATOR] Slack bot modules not available")
            except Exception as e:
                logger.error(f"[ESCALATOR] Failed to initialize Slack bot: {e}")

        # Count enabled channels
        enabled_count = sum(1 for c in self.channels if c.enabled)
        if self.slack_bot:
            enabled_count += 1
        logger.info(f"[ESCALATOR] Initialized with {enabled_count} enabled channels")

    def broadcast(self, report: IncidentReport) -> Dict[str, bool]:
        """
        Broadcast incident report to all enabled channels.

        Args:
            report: Validated incident report

        Returns:
            Dict[str, bool]: Channel name to success status mapping

        Raises:
            EscalatorError: If no channels succeed
            AlertRoutingError: If routing fails
        """
        try:
            # Determine alert level
            alert_level = self._determine_alert_level(report)

            # Format message
            message = self._format_alert_message(report)

            # Send to all enabled channels
            results = {}
            for channel in self.channels:
                if channel.enabled:
                    channel_name = channel.__class__.__name__
                    try:
                        success = channel.send(report, message, alert_level)
                        results[channel_name] = success
                    except NotificationError as e:
                        logger.error(f"[{channel_name}] Notification failed: {e}")
                        results[channel_name] = False

            # Send via Slack bot if enabled
            if self.slack_bot:
                try:
                    thread_ts = self.slack_bot.post_incident(report.model_dump())
                    results['SlackBot'] = thread_ts is not None
                except Exception as e:
                    logger.error(f"[SlackBot] Notification failed: {e}")
                    results['SlackBot'] = False

            # Check if at least one channel succeeded
            if not any(results.values()):
                raise AlertRoutingError(
                    "All notification channels failed",
                    component=self.component_id,
                    context={"results": results}
                )

            # Log summary
            successful = [k for k, v in results.items() if v]
            logger.info(
                f"[ESCALATOR] Alert broadcast: {report.report_id}, "
                f"level={alert_level}, channels={successful}"
            )

            return results

        except AlertRoutingError:
            raise

        except Exception as e:
            raise EscalatorError(
                f"Failed to broadcast alert: {e}",
                component=self.component_id,
                context={"report_id": report.report_id}
            )

    def _determine_alert_level(self, report: IncidentReport) -> str:
        """
        Determine alert level based on incident type and confidence.

        Args:
            report: Incident report

        Returns:
            str: Alert level (CRITICAL, WARNING, INFO)
        """
        # Critical incidents
        if report.incident_type.value in ["DATA_INTEGRITY_FAILURE", "SCHEMA_CHANGE"]:
            if report.final_confidence_score >= 90:
                return "CRITICAL"
            elif report.final_confidence_score >= 70:
                return "WARNING"

        # High confidence on any incident type
        if report.final_confidence_score >= 95:
            return "CRITICAL"

        return "INFO"

    def _format_alert_message(self, report: IncidentReport) -> str:
        """
        Format alert message for display.

        Args:
            report: Incident report

        Returns:
            str: Formatted message
        """
        lines = [
            "=" * 70,
            f"🚨 INCIDENT DETECTED: {report.incident_type.value}",
            "=" * 70,
            f"Report ID: {report.report_id}",
            f"Timestamp: {report.timestamp}",
            f"Status: {report.verification_status.value}",
            f"Confidence: {report.final_confidence_score}%",
            "",
            "ROOT CAUSE:",
            f"  {report.root_cause_analysis}",
            "",
            "EVIDENCE:",
        ]

        for evidence in report.evidence_summary:
            lines.append(f"  • {evidence}")

        lines.append("=" * 70)

        return "\n".join(lines)


# -------------------------------------------------------------------------
# TERMINAL EXECUTION BLOCK
# -------------------------------------------------------------------------
if __name__ == "__main__":
    from config import load_config
    from models import IncidentType, VerificationStatus
    import uuid

    print("\n" + "="*70)
    print("ESCALATOR MODULE - STANDALONE TEST")
    print("="*70 + "\n")

    try:
        # Load configuration
        config = load_config()
        print(f"✓ Configuration loaded: Mode={config.system.mode.value}")

        # Initialize Escalator
        escalator = Escalator(config)
        print(f"✓ Escalator initialized")
        print(f"  Enabled channels: {[c.__class__.__name__ for c in escalator.channels if c.enabled]}\n")

        # Create mock incident report
        mock_report = IncidentReport(
            report_id=str(uuid.uuid4()),
            timestamp=datetime.now().isoformat(),
            incident_type=IncidentType.SCHEMA_CHANGE,
            primary_hypothesis="Test schema mismatch for escalator testing",
            verification_status=VerificationStatus.CONFIRMED,
            final_confidence_score=95.0,
            root_cause_analysis="Test root cause: Schema field renamed without ETL update",
            evidence_summary=[
                "Git: Field renamed from old_name to new_name",
                "ETL: Still expects old_name"
            ]
        )

        # Broadcast alert
        print("--- Broadcasting Test Alert ---")
        results = escalator.broadcast(mock_report)

        # Display results
        print(f"\n--- Notification Results ---")
        for channel, success in results.items():
            status = "✓ SUCCESS" if success else "✗ FAILED"
            print(f"  {channel}: {status}")

        print("\n" + "="*70)
        print("✓ ALL ESCALATOR TESTS PASSED")
        print("="*70 + "\n")

    except Exception as e:
        print(f"\n✗ ESCALATOR TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
