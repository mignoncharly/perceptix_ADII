"""
Message Formatter

Formats Cognizant data into Slack Block Kit messages.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime


class MessageFormatter:
    """
    Formats messages for Slack using Block Kit.
    """

    @staticmethod
    def format_incident(incident: Dict[str, Any], include_buttons: bool = True) -> Dict[str, Any]:
        """
        Format an incident report into a Slack message.

        Args:
            incident: Incident report dictionary
            include_buttons: Whether to include action buttons

        Returns:
            Slack message blocks
        """
        incident_type = incident.get('incident_type', 'UNKNOWN')
        confidence = incident.get('final_confidence_score', 0)
        report_id = incident.get('report_id', 'N/A')
        root_cause = incident.get('root_cause_analysis', 'Analysis pending...')
        criticality = incident.get('criticality', 'UNKNOWN')
        timestamp = incident.get('timestamp', datetime.now().isoformat())

        # Choose emoji based on criticality
        emoji_map = {
            'P0': '🚨',
            'P1': '⚠️',
            'P2': '⚡',
            'P3': 'ℹ️'
        }
        emoji = emoji_map.get(criticality, '🔔')

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} Incident Detected: {incident_type}"
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Report ID:*\n`{report_id}`"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Confidence:*\n{confidence}%"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Criticality:*\n{criticality}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Timestamp:*\n{timestamp[:19]}"
                    }
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Root Cause:*\n{root_cause[:500]}"
                }
            },
            {
                "type": "divider"
            }
        ]

        # Add action buttons if requested
        if include_buttons:
            blocks.append({
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "✓ Acknowledge"
                        },
                        "style": "primary",
                        "value": f"ack:{report_id}",
                        "action_id": "acknowledge_incident"
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "📋 View Details"
                        },
                        "value": f"details:{report_id}",
                        "action_id": "view_details"
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "❌ Ignore"
                        },
                        "style": "danger",
                        "value": f"ignore:{report_id}",
                        "action_id": "ignore_incident"
                    }
                ]
            })

        return {
            "text": f"{emoji} Incident Detected: {incident_type}",
            "blocks": blocks
        }

    @staticmethod
    def format_status(metrics: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format system status into Slack message.

        Args:
            metrics: System metrics dictionary

        Returns:
            Slack message blocks
        """
        counters = metrics.get('counters', {})
        gauges = metrics.get('gauges', {})

        cycles_total = counters.get('cycles_total', 0)
        anomalies = counters.get('anomalies_detected', 0)
        incidents_confirmed = counters.get('incidents_confirmed', 0)
        avg_confidence = gauges.get('avg_confidence_score', 0)

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🤖 Cognizant System Status"
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Total Cycles:*\n{cycles_total}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Anomalies Detected:*\n{anomalies}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Incidents Confirmed:*\n{incidents_confirmed}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Avg Confidence:*\n{avg_confidence:.1f}%"
                    }
                ]
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    }
                ]
            }
        ]

        return {
            "text": "Cognizant System Status",
            "blocks": blocks
        }

    @staticmethod
    def format_incident_list(incidents: List[Dict[str, Any]], limit: int = 10) -> Dict[str, Any]:
        """
        Format a list of incidents into Slack message.

        Args:
            incidents: List of incident dictionaries
            limit: Maximum number to show

        Returns:
            Slack message blocks
        """
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"📊 Recent Incidents (showing {min(len(incidents), limit)})"
                }
            }
        ]

        if not incidents:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "✅ No recent incidents. All systems normal."
                }
            })
        else:
            for idx, incident in enumerate(incidents[:limit]):
                incident_type = incident.get('incident_type', 'UNKNOWN')
                confidence = incident.get('final_confidence_score', 0)
                report_id = incident.get('report_id', 'N/A')[:8]
                timestamp = incident.get('timestamp', '')[:19]

                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*{idx + 1}.* `{report_id}` - *{incident_type}* ({confidence}%)\n_{timestamp}_"
                    }
                })

            if len(incidents) > limit:
                blocks.append({
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"_... and {len(incidents) - limit} more_"
                        }
                    ]
                })

        return {
            "text": f"Recent Incidents ({len(incidents)})",
            "blocks": blocks
        }

    @staticmethod
    def format_daily_summary(incidents: List[Dict[str, Any]], date: str) -> Dict[str, Any]:
        """
        Format daily summary into Slack message.

        Args:
            incidents: List of incidents from the day
            date: Date string

        Returns:
            Slack message blocks
        """
        total = len(incidents)
        by_type = {}
        by_criticality = {}

        for incident in incidents:
            inc_type = incident.get('incident_type', 'UNKNOWN')
            criticality = incident.get('criticality', 'UNKNOWN')

            by_type[inc_type] = by_type.get(inc_type, 0) + 1
            by_criticality[criticality] = by_criticality.get(criticality, 0) + 1

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"📅 Daily Summary - {date}"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Total Incidents:* {total}"
                }
            }
        ]

        if by_type:
            type_text = "\n".join([f"• {k}: {v}" for k, v in by_type.items()])
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*By Type:*\n{type_text}"
                }
            })

        if by_criticality:
            crit_text = "\n".join([f"• {k}: {v}" for k, v in by_criticality.items()])
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*By Criticality:*\n{crit_text}"
                }
            })

        return {
            "text": f"Daily Summary - {date}",
            "blocks": blocks
        }

    @staticmethod
    def format_acknowledgment(incident_id: str, user: str) -> Dict[str, Any]:
        """
        Format acknowledgment confirmation.

        Args:
            incident_id: Incident ID
            user: User who acknowledged

        Returns:
            Slack message blocks
        """
        return {
            "text": f"Incident {incident_id[:8]} acknowledged",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"✅ *Incident acknowledged by <@{user}>*\n`{incident_id}`"
                    }
                }
            ]
        }

    @staticmethod
    def format_error(error_message: str) -> Dict[str, Any]:
        """
        Format error message.

        Args:
            error_message: Error description

        Returns:
            Slack message blocks
        """
        return {
            "text": "Error",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"❌ *Error:* {error_message}"
                    }
                }
            ]
        }

    @staticmethod
    def format_help() -> Dict[str, Any]:
        """
        Format help message with available commands.

        Returns:
            Slack message blocks
        """
        return {
            "text": "Cognizant Bot Help",
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "🤖 Cognizant Bot Commands"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "*Available Commands:*\n\n"
                                "`/cognizant status` - Show system status\n"
                                "`/cognizant incidents [limit]` - List recent incidents\n"
                                "`/cognizant ack <incident_id>` - Acknowledge an incident\n"
                                "`/cognizant help` - Show this help message"
                    }
                }
            ]
        }
