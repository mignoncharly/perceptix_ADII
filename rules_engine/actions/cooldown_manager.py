"""
Rule Cooldown Manager

Manages cooldown periods and rate limiting for rules.
"""

import sqlite3
from typing import Dict, Optional
from datetime import datetime, timedelta
from pathlib import Path


class RuleCooldownManager:
    """
    Manages cooldown periods and rate limiting for rules.

    Prevents alert fatigue by:
    - Enforcing cooldown periods between triggers
    - Limiting daily trigger counts
    """

    def __init__(self, db_path: str = "rules_cooldown.db"):
        """
        Initialize cooldown manager.

        Args:
            db_path: Path to SQLite database for tracking triggers
        """
        self.db_path = db_path
        self._init_database()

    def _init_database(self):
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS rule_triggers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rule_id TEXT NOT NULL,
                    triggered_at TIMESTAMP NOT NULL,
                    context TEXT
                )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_rule_triggers_rule_id
                ON rule_triggers(rule_id)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_rule_triggers_time
                ON rule_triggers(triggered_at)
            """)

            conn.commit()

    def can_trigger(
        self,
        rule_id: str,
        cooldown_minutes: int,
        max_triggers_per_day: int
    ) -> bool:
        """
        Check if a rule can trigger based on cooldown and rate limits.

        Args:
            rule_id: Rule ID
            cooldown_minutes: Cooldown period in minutes
            max_triggers_per_day: Maximum triggers per day

        Returns:
            True if rule can trigger, False otherwise
        """
        # Check cooldown period
        if not self._check_cooldown(rule_id, cooldown_minutes):
            return False

        # Check daily limit
        if not self._check_daily_limit(rule_id, max_triggers_per_day):
            return False

        return True

    def _check_cooldown(self, rule_id: str, cooldown_minutes: int) -> bool:
        """
        Check if cooldown period has elapsed since last trigger.

        Args:
            rule_id: Rule ID
            cooldown_minutes: Cooldown in minutes

        Returns:
            True if cooldown has elapsed or no previous triggers
        """
        if cooldown_minutes == 0:
            return True

        last_trigger = self.get_last_trigger_time(rule_id)

        if last_trigger is None:
            return True

        # Check if enough time has passed
        cooldown_delta = timedelta(minutes=cooldown_minutes)
        time_since_last = datetime.now() - last_trigger

        return time_since_last >= cooldown_delta

    def _check_daily_limit(self, rule_id: str, max_triggers_per_day: int) -> bool:
        """
        Check if daily trigger limit has been reached.

        Args:
            rule_id: Rule ID
            max_triggers_per_day: Maximum triggers per day

        Returns:
            True if under limit
        """
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT COUNT(*) FROM rule_triggers
                WHERE rule_id = ?
                AND triggered_at >= ?
            """, (rule_id, today_start.isoformat()))

            count = cursor.fetchone()[0]

        return count < max_triggers_per_day

    def record_trigger(self, rule_id: str, context: Optional[str] = None):
        """
        Record that a rule has triggered.

        Args:
            rule_id: Rule ID
            context: Optional context string
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO rule_triggers (rule_id, triggered_at, context)
                VALUES (?, ?, ?)
            """, (rule_id, datetime.now().isoformat(), context))
            conn.commit()

    def get_last_trigger_time(self, rule_id: str) -> Optional[datetime]:
        """
        Get the last time a rule triggered.

        Args:
            rule_id: Rule ID

        Returns:
            Last trigger time or None if never triggered
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT triggered_at FROM rule_triggers
                WHERE rule_id = ?
                ORDER BY triggered_at DESC
                LIMIT 1
            """, (rule_id,))

            row = cursor.fetchone()

            if row:
                return datetime.fromisoformat(row[0])

        return None

    def get_trigger_count(
        self,
        rule_id: str,
        since: Optional[datetime] = None
    ) -> int:
        """
        Get number of times a rule has triggered.

        Args:
            rule_id: Rule ID
            since: Optional start time (defaults to today)

        Returns:
            Trigger count
        """
        if since is None:
            since = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT COUNT(*) FROM rule_triggers
                WHERE rule_id = ?
                AND triggered_at >= ?
            """, (rule_id, since.isoformat()))

            return cursor.fetchone()[0]

    def get_time_until_next_trigger(
        self,
        rule_id: str,
        cooldown_minutes: int
    ) -> Optional[timedelta]:
        """
        Get time remaining until rule can trigger again.

        Args:
            rule_id: Rule ID
            cooldown_minutes: Cooldown in minutes

        Returns:
            Time remaining or None if can trigger now
        """
        last_trigger = self.get_last_trigger_time(rule_id)

        if last_trigger is None:
            return None

        cooldown_delta = timedelta(minutes=cooldown_minutes)
        time_since_last = datetime.now() - last_trigger

        if time_since_last >= cooldown_delta:
            return None

        return cooldown_delta - time_since_last

    def clear_old_triggers(self, days_to_keep: int = 30):
        """
        Clear old trigger records to keep database size manageable.

        Args:
            days_to_keep: Number of days of history to keep
        """
        cutoff_date = datetime.now() - timedelta(days=days_to_keep)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                DELETE FROM rule_triggers
                WHERE triggered_at < ?
            """, (cutoff_date.isoformat(),))
            conn.commit()

    def get_rule_stats(self, rule_id: str) -> Dict[str, any]:
        """
        Get statistics for a rule.

        Args:
            rule_id: Rule ID

        Returns:
            Dictionary with stats
        """
        last_trigger = self.get_last_trigger_time(rule_id)
        today_count = self.get_trigger_count(rule_id)

        # Get total count
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT COUNT(*) FROM rule_triggers
                WHERE rule_id = ?
            """, (rule_id,))
            total_count = cursor.fetchone()[0]

        return {
            'rule_id': rule_id,
            'total_triggers': total_count,
            'today_triggers': today_count,
            'last_triggered': last_trigger.isoformat() if last_trigger else None
        }

    def reset_rule_triggers(self, rule_id: str):
        """
        Reset all triggers for a rule (useful for testing or rule updates).

        Args:
            rule_id: Rule ID
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                DELETE FROM rule_triggers
                WHERE rule_id = ?
            """, (rule_id,))
            conn.commit()
