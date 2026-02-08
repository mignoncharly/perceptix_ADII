"""
Incident Acknowledgment Tracker

Tracks which incidents have been acknowledged by users.
"""

import sqlite3
from typing import List, Optional, Dict, Any
from datetime import datetime
from pathlib import Path


class IncidentAcknowledger:
    """
    Manages incident acknowledgments.
    """

    def __init__(self, db_path: str = "incident_acks.db"):
        """
        Initialize acknowledgment tracker.

        Args:
            db_path: Path to SQLite database
        """
        self.db_path = db_path
        self._init_database()

    def _init_database(self):
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS incident_acknowledgments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    incident_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    user_name TEXT,
                    acknowledged_at TIMESTAMP NOT NULL,
                    notes TEXT,
                    UNIQUE(incident_id, user_id)
                )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_ack_incident
                ON incident_acknowledgments(incident_id)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_ack_user
                ON incident_acknowledgments(user_id)
            """)

            conn.commit()

    def acknowledge(
        self,
        incident_id: str,
        user_id: str,
        user_name: Optional[str] = None,
        notes: Optional[str] = None
    ) -> bool:
        """
        Record an incident acknowledgment.

        Args:
            incident_id: Incident report ID
            user_id: User ID who acknowledged
            user_name: Optional user display name
            notes: Optional acknowledgment notes

        Returns:
            True if acknowledgment was recorded, False if already acknowledged
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR IGNORE INTO incident_acknowledgments
                    (incident_id, user_id, user_name, acknowledged_at, notes)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    incident_id,
                    user_id,
                    user_name,
                    datetime.now().isoformat(),
                    notes
                ))

                # Check if row was inserted
                cursor = conn.execute("""
                    SELECT changes()
                """)
                changes = cursor.fetchone()[0]

                conn.commit()
                return changes > 0

        except sqlite3.Error as e:
            print(f"Error acknowledging incident: {e}")
            return False

    def is_acknowledged(self, incident_id: str) -> bool:
        """
        Check if an incident has been acknowledged.

        Args:
            incident_id: Incident report ID

        Returns:
            True if acknowledged by at least one user
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT COUNT(*) FROM incident_acknowledgments
                WHERE incident_id = ?
            """, (incident_id,))

            count = cursor.fetchone()[0]
            return count > 0

    def get_acknowledgments(self, incident_id: str) -> List[Dict[str, Any]]:
        """
        Get all acknowledgments for an incident.

        Args:
            incident_id: Incident report ID

        Returns:
            List of acknowledgment dictionaries
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT user_id, user_name, acknowledged_at, notes
                FROM incident_acknowledgments
                WHERE incident_id = ?
                ORDER BY acknowledged_at ASC
            """, (incident_id,))

            acks = []
            for row in cursor.fetchall():
                acks.append({
                    'user_id': row[0],
                    'user_name': row[1],
                    'acknowledged_at': row[2],
                    'notes': row[3]
                })

            return acks

    def get_unacknowledged(
        self,
        incident_ids: List[str]
    ) -> List[str]:
        """
        Get list of unacknowledged incidents from a list.

        Args:
            incident_ids: List of incident IDs to check

        Returns:
            List of unacknowledged incident IDs
        """
        if not incident_ids:
            return []

        unacknowledged = []
        for incident_id in incident_ids:
            if not self.is_acknowledged(incident_id):
                unacknowledged.append(incident_id)

        return unacknowledged

    def get_user_acknowledgments(
        self,
        user_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get recent acknowledgments by a user.

        Args:
            user_id: User ID
            limit: Maximum number to return

        Returns:
            List of acknowledgment dictionaries
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT incident_id, acknowledged_at, notes
                FROM incident_acknowledgments
                WHERE user_id = ?
                ORDER BY acknowledged_at DESC
                LIMIT ?
            """, (user_id, limit))

            acks = []
            for row in cursor.fetchall():
                acks.append({
                    'incident_id': row[0],
                    'acknowledged_at': row[1],
                    'notes': row[2]
                })

            return acks

    def get_stats(self) -> Dict[str, Any]:
        """
        Get acknowledgment statistics.

        Returns:
            Dictionary with stats
        """
        with sqlite3.connect(self.db_path) as conn:
            # Total acknowledgments
            cursor = conn.execute("""
                SELECT COUNT(DISTINCT incident_id) as total_incidents,
                       COUNT(*) as total_acks
                FROM incident_acknowledgments
            """)
            row = cursor.fetchone()
            total_incidents = row[0]
            total_acks = row[1]

            # Top acknowledgers
            cursor = conn.execute("""
                SELECT user_id, user_name, COUNT(*) as ack_count
                FROM incident_acknowledgments
                GROUP BY user_id
                ORDER BY ack_count DESC
                LIMIT 5
            """)

            top_users = []
            for row in cursor.fetchall():
                top_users.append({
                    'user_id': row[0],
                    'user_name': row[1],
                    'ack_count': row[2]
                })

            return {
                'total_incidents_acknowledged': total_incidents,
                'total_acknowledgments': total_acks,
                'top_acknowledgers': top_users
            }

    def clear_old_acknowledgments(self, days_to_keep: int = 90):
        """
        Clear old acknowledgment records.

        Args:
            days_to_keep: Number of days to keep
        """
        from datetime import timedelta

        cutoff_date = datetime.now() - timedelta(days=days_to_keep)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                DELETE FROM incident_acknowledgments
                WHERE acknowledged_at < ?
            """, (cutoff_date.isoformat(),))
            conn.commit()
