"""
Historian Module: Memory System
Persists incident reports to database with proper error handling.
"""
import logging
import json
from datetime import datetime, timezone
from typing import List, Tuple, Any
from typing import Dict

from database import DatabaseManager
from models import IncidentReport
from exceptions import HistorianError

logger = logging.getLogger("PerceptixHistorian")

class Historian:
    """
    The Memory System.
    Persists incident reports to database with proper error handling.
    """

    def __init__(self, db_manager: DatabaseManager):
        """
        Initialize Historian with database manager.

        Args:
            db_manager: Database manager instance
        """
        self.db_manager = db_manager
        self.component_id = "HISTORIAN_V1"

    def save_incident(self, report: IncidentReport, tenant_id: str | None = None) -> None:
        """
        Save incident report to database.

        Args:
            report: Validated incident report

        Raises:
            HistorianError: If save fails
        """
        try:
            with self.db_manager.transaction() as conn:
                conn.execute(
                    """INSERT INTO incidents
                       (id, tenant_id, timestamp, type, confidence, summary, status, full_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        report.report_id,
                        tenant_id,
                        report.timestamp,
                        report.incident_type.value,
                        report.final_confidence_score,
                        report.root_cause_analysis,
                        report.status,
                        report.model_dump_json()
                    )
                )
                conn.commit()

            logger.info(f"[HISTORIAN] Incident {report.report_id} archived successfully")

        except Exception as e:
            raise HistorianError(
                f"Failed to save incident: {e}",
                component=self.component_id,
                context={"report_id": report.report_id}
            )

    def get_recent_incidents(self, limit: int = 10, incident_type: str = None,
                             confidence_min: float = None,
                             timestamp_after: str = None,
                             include_archived: bool = False,
                             status: str = None) -> List[Tuple]:
        """
        Retrieve recent incidents with optional filtering.
        """
        try:
            query = "SELECT id, timestamp, type, confidence, status, summary FROM incidents"
            params = []
            where_clauses = []

            if incident_type:
                where_clauses.append("type = ?")
                params.append(incident_type)
            
            if confidence_min is not None:
                where_clauses.append("confidence >= ?")
                params.append(confidence_min)
                
            if timestamp_after:
                where_clauses.append("timestamp >= ?")
                params.append(timestamp_after)

            if status:
                where_clauses.append("status = ?")
                params.append(status)

            if not include_archived:
                where_clauses.append("status != ?")
                params.append("ARCHIVED")

            if where_clauses:
                query += " WHERE " + " AND ".join(where_clauses)
            
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)

            with self.db_manager.connection() as conn:
                cursor = conn.execute(query, tuple(params))
                results = cursor.fetchall()

            return results

        except Exception as e:
            raise HistorianError(
                f"Failed to retrieve incidents: {e}",
                component=self.component_id
            )

    def archive_incident(self, report_id: str) -> bool:
        """Archive an incident by setting status to ARCHIVED."""
        try:
            archived_at = datetime.now(timezone.utc).isoformat()
            with self.db_manager.transaction() as conn:
                cursor = conn.execute(
                    "UPDATE incidents SET status = ?, archived_at = ? WHERE id = ? AND status != ?",
                    ("ARCHIVED", archived_at, report_id, "ARCHIVED")
                )
                conn.commit()
                return (cursor.rowcount or 0) > 0
        except Exception as e:
            raise HistorianError(
                f"Failed to archive incident: {e}",
                component=self.component_id,
                context={"report_id": report_id}
            )

    def delete_incident(self, report_id: str) -> bool:
        """Permanently delete an incident."""
        try:
            with self.db_manager.transaction() as conn:
                cursor = conn.execute(
                    "DELETE FROM incidents WHERE id = ?",
                    (report_id,)
                )
                conn.commit()
                return (cursor.rowcount or 0) > 0
        except Exception as e:
            raise HistorianError(
                f"Failed to delete incident: {e}",
                component=self.component_id,
                context={"report_id": report_id}
            )

    def bulk_archive_incidents(self, report_ids: List[str]) -> int:
        """Archive multiple incidents by ID."""
        if not report_ids:
            return 0

        try:
            archived_at = datetime.now(timezone.utc).isoformat()
            placeholders = ",".join(["?"] * len(report_ids))
            with self.db_manager.transaction() as conn:
                cursor = conn.execute(
                    f"UPDATE incidents SET status = ?, archived_at = ? WHERE id IN ({placeholders}) AND status != ?",
                    ("ARCHIVED", archived_at, *report_ids, "ARCHIVED")
                )
                conn.commit()
                return int(cursor.rowcount or 0)
        except Exception as e:
            raise HistorianError(
                f"Failed to bulk archive incidents: {e}",
                component=self.component_id,
                context={"count": len(report_ids)}
            )

    def record_audit_event(
        self,
        actor: str,
        action: str,
        entity_type: str,
        entity_id: str | None = None,
        details: Dict[str, Any] | None = None,
    ) -> None:
        """Persist an audit event for operator actions."""
        try:
            details_json = json.dumps(details or {}, default=str)
            with self.db_manager.transaction() as conn:
                conn.execute(
                    """
                    INSERT INTO audit_events (actor, action, entity_type, entity_id, details_json)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (actor, action, entity_type, entity_id, details_json),
                )
                conn.commit()
        except Exception as e:
            raise HistorianError(
                f"Failed to record audit event: {e}",
                component=self.component_id,
                context={"actor": actor, "action": action, "entity_type": entity_type, "entity_id": entity_id},
            )

    def get_dashboard_trends(self, days: int = 7) -> Dict[str, Any]:
        """
        Return trends and MTTR statistics based on persisted incidents.

        MTTR is computed as (archived_at - timestamp) for archived incidents.
        """
        try:
            if days < 1 or days > 90:
                raise ValueError("days must be between 1 and 90")

            with self.db_manager.connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT id, timestamp, status, archived_at
                    FROM incidents
                    ORDER BY timestamp DESC
                    """
                )
                rows = cursor.fetchall()

            # Build day buckets in UTC (YYYY-MM-DD)
            now = datetime.now(timezone.utc)
            cutoff = now.timestamp() - (days * 86400)

            def _parse_ts(ts: str | None) -> float | None:
                if not ts:
                    return None
                # Handle ISO or SQLite CURRENT_TIMESTAMP.
                try:
                    return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
                except Exception:
                    pass
                try:
                    return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
                except Exception:
                    return None

            by_day: Dict[str, Dict[str, int]] = {}
            mttr_minutes: list[float] = []

            for _id, ts, status, archived_at in rows:
                ts_epoch = _parse_ts(ts)
                if ts_epoch is None or ts_epoch < cutoff:
                    continue
                day = datetime.fromtimestamp(ts_epoch, tz=timezone.utc).strftime("%Y-%m-%d")
                bucket = by_day.setdefault(day, {"detected": 0, "archived": 0})
                bucket["detected"] += 1
                if str(status).upper() == "ARCHIVED":
                    bucket["archived"] += 1
                    archived_epoch = _parse_ts(archived_at)
                    if archived_epoch is not None:
                        mttr_minutes.append(max(0.0, (archived_epoch - ts_epoch) / 60.0))

            # Fill missing days so chart lines are continuous
            timeline = []
            for i in range(days - 1, -1, -1):
                day = datetime.fromtimestamp(now.timestamp() - i * 86400, tz=timezone.utc).strftime("%Y-%m-%d")
                bucket = by_day.get(day, {"detected": 0, "archived": 0})
                timeline.append({"date": day, **bucket})

            mttr_avg = (sum(mttr_minutes) / len(mttr_minutes)) if mttr_minutes else None
            mttr_p95 = None
            if mttr_minutes:
                sorted_vals = sorted(mttr_minutes)
                idx = int(round(0.95 * (len(sorted_vals) - 1)))
                mttr_p95 = sorted_vals[idx]

            return {
                "days": days,
                "timeline": timeline,
                "mttr_minutes_avg": mttr_avg,
                "mttr_minutes_p95": mttr_p95,
                "archived_sample_count": len(mttr_minutes),
                "incidents_total_window": sum(p["detected"] for p in timeline),
            }
        except Exception as e:
            raise HistorianError(
                f"Failed to build dashboard trends: {e}",
                component=self.component_id,
            )

    def bulk_delete_incidents(self, report_ids: List[str]) -> int:
        """Permanently delete multiple incidents by ID."""
        if not report_ids:
            return 0

        try:
            placeholders = ",".join(["?"] * len(report_ids))
            with self.db_manager.transaction() as conn:
                cursor = conn.execute(
                    f"DELETE FROM incidents WHERE id IN ({placeholders})",
                    tuple(report_ids)
                )
                conn.commit()
                return int(cursor.rowcount or 0)
        except Exception as e:
            raise HistorianError(
                f"Failed to bulk delete incidents: {e}",
                component=self.component_id,
                context={"count": len(report_ids)}
            )

    def reset_demo_data(self) -> Dict[str, int]:
        """
        Clear dashboard demo data for clean re-recording sessions.

        Returns:
            Dict with counts of deleted incidents and metric points.
        """
        try:
            with self.db_manager.transaction() as conn:
                incidents_deleted = int(
                    (conn.execute("DELETE FROM incidents").rowcount or 0)
                )
                metrics_deleted = int(
                    (conn.execute("DELETE FROM metrics_timeseries").rowcount or 0)
                )
                approvals_deleted = int(
                    (conn.execute("DELETE FROM remediation_approvals").rowcount or 0)
                ) if self._table_exists(conn, "remediation_approvals") else 0
                executions_deleted = int(
                    (conn.execute("DELETE FROM remediation_executions").rowcount or 0)
                ) if self._table_exists(conn, "remediation_executions") else 0
                policies_deleted = int(
                    (conn.execute("DELETE FROM policies").rowcount or 0)
                ) if self._table_exists(conn, "policies") else 0
                events_deleted = int(
                    (conn.execute("DELETE FROM pipeline_events").rowcount or 0)
                ) if self._table_exists(conn, "pipeline_events") else 0
                conn.commit()

            logger.warning(
                "[HISTORIAN] Demo data reset completed "
                f"(incidents_deleted={incidents_deleted}, metrics_deleted={metrics_deleted})"
            )
            return {
                "incidents_deleted": incidents_deleted,
                "metrics_deleted": metrics_deleted,
                "approvals_deleted": approvals_deleted,
                "executions_deleted": executions_deleted,
                "policies_deleted": policies_deleted,
                "pipeline_events_deleted": events_deleted,
            }
        except Exception as e:
            raise HistorianError(
                f"Failed to reset demo data: {e}",
                component=self.component_id,
            )

    def _table_exists(self, conn: Any, table_name: str) -> bool:
        try:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,),
            )
            return cursor.fetchone() is not None
        except Exception:
            return False

    # ---------------------------------------------------------------------
    # Pipeline Events (Webhook / Orchestration Ingestion)
    # ---------------------------------------------------------------------

    def record_pipeline_event(
        self,
        event_id: str,
        tenant_id: str | None,
        source: str,
        pipeline: str,
        run_id: str | None,
        status: str,
        severity: str,
        message: str | None,
        metrics: Dict[str, Any] | None,
        event_timestamp: str,
    ) -> None:
        try:
            metrics_json = json.dumps(metrics or {}, default=str)
            with self.db_manager.transaction() as conn:
                conn.execute(
                    """
                    INSERT INTO pipeline_events
                      (id, tenant_id, source, pipeline, run_id, status, severity, message, metrics_json, event_timestamp)
                    VALUES
                      (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event_id,
                        tenant_id,
                        source,
                        pipeline,
                        run_id,
                        status,
                        severity,
                        message,
                        metrics_json,
                        event_timestamp,
                    ),
                )
                conn.commit()
        except Exception as e:
            raise HistorianError(
                f"Failed to record pipeline event: {e}",
                component=self.component_id,
                context={"event_id": event_id, "pipeline": pipeline},
            )

    # ---------------------------------------------------------------------
    # Policies (Automation Routing)
    # ---------------------------------------------------------------------

    def upsert_policy(
        self,
        policy_id: str,
        name: str,
        enabled: bool,
        match: Dict[str, Any],
        action: Dict[str, Any],
    ) -> None:
        try:
            match_json = json.dumps(match or {}, default=str)
            action_json = json.dumps(action or {}, default=str)
            with self.db_manager.transaction() as conn:
                conn.execute(
                    """
                    INSERT INTO policies (id, name, enabled, match_json, action_json, updated_at)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(id) DO UPDATE SET
                      name=excluded.name,
                      enabled=excluded.enabled,
                      match_json=excluded.match_json,
                      action_json=excluded.action_json,
                      updated_at=CURRENT_TIMESTAMP
                    """,
                    (policy_id, name, 1 if enabled else 0, match_json, action_json),
                )
                conn.commit()
        except Exception as e:
            raise HistorianError(
                f"Failed to upsert policy: {e}",
                component=self.component_id,
                context={"policy_id": policy_id},
            )

    def delete_policy(self, policy_id: str) -> bool:
        try:
            with self.db_manager.transaction() as conn:
                cursor = conn.execute("DELETE FROM policies WHERE id = ?", (policy_id,))
                conn.commit()
                return int(cursor.rowcount or 0) > 0
        except Exception as e:
            raise HistorianError(
                f"Failed to delete policy: {e}",
                component=self.component_id,
                context={"policy_id": policy_id},
            )

    def list_policies(self, enabled_only: bool = False) -> list[Dict[str, Any]]:
        try:
            query = "SELECT id, name, enabled, match_json, action_json, created_at, updated_at FROM policies"
            params: list[Any] = []
            if enabled_only:
                query += " WHERE enabled = ?"
                params.append(1)
            query += " ORDER BY created_at DESC"
            with self.db_manager.connection() as conn:
                rows = conn.execute(query, tuple(params)).fetchall()
            out: list[Dict[str, Any]] = []
            for r in rows:
                out.append(
                    {
                        "id": r[0],
                        "name": r[1],
                        "enabled": bool(r[2]),
                        "match": json.loads(r[3] or "{}"),
                        "action": json.loads(r[4] or "{}"),
                        "created_at": r[5],
                        "updated_at": r[6],
                    }
                )
            return out
        except Exception as e:
            raise HistorianError(
                f"Failed to list policies: {e}",
                component=self.component_id,
            )

    # ---------------------------------------------------------------------
    # Remediation Approvals (Persistent Approval Gates)
    # ---------------------------------------------------------------------

    def create_remediation_approval(
        self,
        token_id: str,
        tenant_id: str | None,
        incident_id: str,
        playbook_name: str,
        status: str,
        requested_at: str,
        expires_at: str,
        requested_by: str | None,
        context: Dict[str, Any] | None,
        details: Dict[str, Any] | None,
    ) -> None:
        try:
            context_json = json.dumps(context or {}, default=str)
            details_json = json.dumps(details or {}, default=str)
            with self.db_manager.transaction() as conn:
                conn.execute(
                    """
                    INSERT INTO remediation_approvals
                      (token_id, tenant_id, incident_id, playbook_name, status, requested_at, expires_at,
                       requested_by, context_json, details_json)
                    VALUES
                      (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        token_id,
                        tenant_id,
                        incident_id,
                        playbook_name,
                        status,
                        requested_at,
                        expires_at,
                        requested_by,
                        context_json,
                        details_json,
                    ),
                )
                conn.commit()
        except Exception as e:
            raise HistorianError(
                f"Failed to create remediation approval: {e}",
                component=self.component_id,
                context={"token_id": token_id, "incident_id": incident_id, "playbook": playbook_name},
            )

    def get_pending_remediation_approvals(self) -> list[Dict[str, Any]]:
        try:
            with self.db_manager.connection() as conn:
                rows = conn.execute(
                    """
                    SELECT token_id, incident_id, playbook_name, status, requested_at, expires_at, details_json
                    FROM remediation_approvals
                    WHERE status = ?
                    ORDER BY requested_at DESC
                    """,
                    ("pending",),
                ).fetchall()
            out: list[Dict[str, Any]] = []
            for r in rows:
                out.append(
                    {
                        "token_id": r[0],
                        "incident_id": r[1],
                        "playbook_name": r[2],
                        "status": r[3],
                        "requested_at": r[4],
                        "expires_at": r[5],
                        "details": json.loads(r[6] or "{}"),
                    }
                )
            return out
        except Exception as e:
            raise HistorianError(
                f"Failed to get pending approvals: {e}",
                component=self.component_id,
            )

    def get_remediation_approval(self, token_id: str) -> Dict[str, Any] | None:
        try:
            with self.db_manager.connection() as conn:
                row = conn.execute(
                    """
                    SELECT token_id, tenant_id, incident_id, playbook_name, status,
                           requested_at, expires_at, requested_by, approved_by, comment,
                           context_json, details_json
                    FROM remediation_approvals
                    WHERE token_id = ?
                    """,
                    (token_id,),
                ).fetchone()
            if not row:
                return None
            return {
                "token_id": row[0],
                "tenant_id": row[1],
                "incident_id": row[2],
                "playbook_name": row[3],
                "status": row[4],
                "requested_at": row[5],
                "expires_at": row[6],
                "requested_by": row[7],
                "approved_by": row[8],
                "comment": row[9],
                "context": json.loads(row[10] or "{}"),
                "details": json.loads(row[11] or "{}"),
            }
        except Exception as e:
            raise HistorianError(
                f"Failed to get remediation approval: {e}",
                component=self.component_id,
                context={"token_id": token_id},
            )

    def update_remediation_approval_status(
        self,
        token_id: str,
        status: str,
        approved_by: str | None = None,
        comment: str | None = None,
    ) -> bool:
        try:
            with self.db_manager.transaction() as conn:
                cursor = conn.execute(
                    """
                    UPDATE remediation_approvals
                    SET status = ?, approved_by = ?, comment = ?
                    WHERE token_id = ?
                    """,
                    (status, approved_by, comment, token_id),
                )
                conn.commit()
                return int(cursor.rowcount or 0) > 0
        except Exception as e:
            raise HistorianError(
                f"Failed to update remediation approval status: {e}",
                component=self.component_id,
                context={"token_id": token_id, "status": status},
            )

    def record_remediation_execution(
        self,
        tenant_id: str | None,
        incident_id: str,
        playbook_name: str,
        success: bool,
        started_at: str,
        finished_at: str,
        execution: Dict[str, Any] | None,
    ) -> None:
        try:
            execution_json = json.dumps(execution or {}, default=str)
            with self.db_manager.transaction() as conn:
                conn.execute(
                    """
                    INSERT INTO remediation_executions
                      (tenant_id, incident_id, playbook_name, success, started_at, finished_at, execution_json)
                    VALUES
                      (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        tenant_id,
                        incident_id,
                        playbook_name,
                        1 if success else 0,
                        started_at,
                        finished_at,
                        execution_json,
                    ),
                )
                conn.commit()
        except Exception as e:
            raise HistorianError(
                f"Failed to record remediation execution: {e}",
                component=self.component_id,
                context={"incident_id": incident_id, "playbook": playbook_name},
            )

    def save_metric(self, name: str, value: float, tags: str = None) -> None:
        """Save a metric data point."""
        try:
            with self.db_manager.transaction() as conn:
                conn.execute(
                    "INSERT INTO metrics_timeseries (metric_name, value, tags) VALUES (?, ?, ?)",
                    (name, value, tags)
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to save metric {name}: {e}")

    def get_incident_statistics(self, active_since: str = None, include_archived: bool = False) -> Dict[str, int]:
        """
        Get aggregate incident statistics for dashboard usage.

        Args:
            active_since: ISO timestamp cutoff for active incident count
            include_archived: Whether archived incidents should be included

        Returns:
            Dict with total, critical, and active counts
        """
        try:
            where_clauses = []
            params: List[Any] = []

            if not include_archived:
                where_clauses.append("status != ?")
                params.append("ARCHIVED")

            where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

            with self.db_manager.connection() as conn:
                cursor = conn.execute(
                    f"""
                    SELECT
                        COUNT(*) AS total_count,
                        SUM(CASE WHEN confidence >= 90.0 THEN 1 ELSE 0 END) AS critical_count
                    FROM incidents
                    {where_sql}
                    """,
                    tuple(params),
                )
                row = cursor.fetchone()

                total_count = int(row[0] or 0) if row else 0
                critical_count = int(row[1] or 0) if row else 0

                active_count = 0
                if active_since:
                    active_where_sql = where_sql
                    active_params = list(params)
                    if active_where_sql:
                        active_where_sql += " AND timestamp >= ?"
                    else:
                        active_where_sql = "WHERE timestamp >= ?"
                    active_params.append(active_since)

                    active_cursor = conn.execute(
                        f"""
                        SELECT COUNT(*)
                        FROM incidents
                        {active_where_sql}
                        """,
                        tuple(active_params),
                    )
                    active_row = active_cursor.fetchone()
                    active_count = int(active_row[0] or 0) if active_row else 0

            return {
                "total": total_count,
                "critical": critical_count,
                "active": active_count,
            }
        except Exception as e:
            raise HistorianError(
                f"Failed to retrieve incident statistics: {e}",
                component=self.component_id
            )
