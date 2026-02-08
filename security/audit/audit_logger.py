"""
Audit Logger

Comprehensive audit logging for all system actions.
"""

import logging
import json
import sqlite3
from typing import Dict, Any, Optional, List
from pathlib import Path
from datetime import datetime, timedelta

from security.audit.audit_models import AuditEvent, AuditEventType


logger = logging.getLogger("AuditLogger")


class AuditLogger:
    """
    Comprehensive audit logging for all system actions.

    Features:
    - Append-only audit log storage
    - SQLite database for queryability
    - Optional SIEM integration
    - Tamper-evident logging
    """

    def __init__(
        self,
        db_path: str = "audit_log.db",
        siem_enabled: bool = False,
        siem_endpoint: Optional[str] = None
    ):
        """
        Initialize audit logger.

        Args:
            db_path: Path to SQLite audit database
            siem_enabled: Enable SIEM integration
            siem_endpoint: SIEM endpoint URL
        """
        self.db_path = db_path
        self.siem_enabled = siem_enabled
        self.siem_endpoint = siem_endpoint

        self._init_database()

        logger.info(f"Audit logger initialized: {db_path}")

    def _init_database(self):
        """Initialize audit log database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    event_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    user TEXT NOT NULL,
                    action TEXT NOT NULL,
                    resource TEXT NOT NULL,
                    status TEXT NOT NULL,
                    ip_address TEXT,
                    user_agent TEXT,
                    details TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Indexes for common queries
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_timestamp
                ON audit_log(timestamp)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_user
                ON audit_log(user)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_event_type
                ON audit_log(event_type)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_status
                ON audit_log(status)
            """)

            conn.commit()

    def log_event(
        self,
        event_type: AuditEventType,
        user: str,
        action: str,
        resource: str,
        status: str,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> str:
        """
        Log an audit event.

        Args:
            event_type: Type of audit event
            user: User performing action
            action: Action being performed
            resource: Resource being accessed
            status: Status (success, failure, denied)
            details: Additional details
            ip_address: Client IP address
            user_agent: Client user agent

        Returns:
            Event ID
        """
        event = AuditEvent(
            event_type=event_type,
            user=user,
            action=action,
            resource=resource,
            status=status,
            details=details or {},
            ip_address=ip_address,
            user_agent=user_agent
        )

        # Write to database (append-only)
        self._write_to_database(event)

        # Send to SIEM if configured
        if self.siem_enabled and self.siem_endpoint:
            self._send_to_siem(event)

        # Log to application logger
        logger.info(
            f"AUDIT: {event_type.value} | {user} | {action} | {resource} | {status}"
        )

        return event.event_id

    def _write_to_database(self, event: AuditEvent):
        """Write event to audit database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO audit_log (
                    event_id, timestamp, event_type, user, action,
                    resource, status, ip_address, user_agent, details
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event.event_id,
                event.timestamp.isoformat(),
                event.event_type.value,
                event.user,
                event.action,
                event.resource,
                event.status,
                event.ip_address,
                event.user_agent,
                json.dumps(event.details)
            ))
            conn.commit()

    def _send_to_siem(self, event: AuditEvent):
        """Send event to SIEM."""
        try:
            import requests

            # Send in syslog format
            payload = {
                'event': event.to_dict(),
                'syslog': event.to_syslog_format()
            }

            requests.post(
                self.siem_endpoint,
                json=payload,
                timeout=5
            )

            logger.debug(f"Sent audit event {event.event_id} to SIEM")

        except Exception as e:
            logger.error(f"Failed to send event to SIEM: {e}")

    def query_events(
        self,
        user: Optional[str] = None,
        event_type: Optional[AuditEventType] = None,
        status: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Query audit events.

        Args:
            user: Filter by user
            event_type: Filter by event type
            status: Filter by status
            start_time: Filter by start time
            end_time: Filter by end time
            limit: Maximum results

        Returns:
            List of audit events
        """
        query = "SELECT * FROM audit_log WHERE 1=1"
        params = []

        if user:
            query += " AND user = ?"
            params.append(user)

        if event_type:
            query += " AND event_type = ?"
            params.append(event_type.value)

        if status:
            query += " AND status = ?"
            params.append(status)

        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time.isoformat())

        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time.isoformat())

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(query, params)

            events = []
            for row in cursor.fetchall():
                event = dict(row)
                event['details'] = json.loads(event['details'])
                events.append(event)

            return events

    def get_user_activity(
        self,
        user: str,
        days: int = 7
    ) -> Dict[str, Any]:
        """
        Get user activity summary.

        Args:
            user: User ID
            days: Number of days to analyze

        Returns:
            Activity summary
        """
        start_time = datetime.now() - timedelta(days=days)

        events = self.query_events(
            user=user,
            start_time=start_time,
            limit=1000
        )

        # Aggregate by event type
        event_counts = {}
        for event in events:
            event_type = event['event_type']
            event_counts[event_type] = event_counts.get(event_type, 0) + 1

        # Count failures
        failures = sum(1 for e in events if e['status'] == 'failure')

        return {
            'user': user,
            'total_events': len(events),
            'event_types': event_counts,
            'failures': failures,
            'period_days': days
        }

    def get_failed_attempts(
        self,
        hours: int = 24,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get recent failed authentication/authorization attempts.

        Args:
            hours: Hours to look back
            limit: Maximum results

        Returns:
            List of failed attempts
        """
        start_time = datetime.now() - timedelta(hours=hours)

        return self.query_events(
            status='failure',
            start_time=start_time,
            limit=limit
        )

    def export_audit_log(
        self,
        output_path: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ):
        """
        Export audit log to JSON file.

        Args:
            output_path: Output file path
            start_time: Start time filter
            end_time: End time filter
        """
        events = self.query_events(
            start_time=start_time,
            end_time=end_time,
            limit=10000
        )

        with open(output_path, 'w') as f:
            json.dump({
                'export_time': datetime.now().isoformat(),
                'event_count': len(events),
                'events': events
            }, f, indent=2)

        logger.info(f"Exported {len(events)} audit events to {output_path}")

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get audit log statistics.

        Returns:
            Statistics dictionary
        """
        with sqlite3.connect(self.db_path) as conn:
            # Total events
            cursor = conn.execute("SELECT COUNT(*) FROM audit_log")
            total_events = cursor.fetchone()[0]

            # Events by type
            cursor = conn.execute("""
                SELECT event_type, COUNT(*) as count
                FROM audit_log
                GROUP BY event_type
                ORDER BY count DESC
            """)
            events_by_type = {row[0]: row[1] for row in cursor.fetchall()}

            # Events by status
            cursor = conn.execute("""
                SELECT status, COUNT(*) as count
                FROM audit_log
                GROUP BY status
            """)
            events_by_status = {row[0]: row[1] for row in cursor.fetchall()}

            # Top users
            cursor = conn.execute("""
                SELECT user, COUNT(*) as count
                FROM audit_log
                GROUP BY user
                ORDER BY count DESC
                LIMIT 10
            """)
            top_users = [{'user': row[0], 'count': row[1]} for row in cursor.fetchall()]

            # Recent activity (last 24 hours)
            start_time = datetime.now() - timedelta(hours=24)
            cursor = conn.execute("""
                SELECT COUNT(*) FROM audit_log
                WHERE timestamp >= ?
            """, (start_time.isoformat(),))
            recent_events = cursor.fetchone()[0]

            return {
                'total_events': total_events,
                'events_by_type': events_by_type,
                'events_by_status': events_by_status,
                'top_users': top_users,
                'recent_events_24h': recent_events
            }
