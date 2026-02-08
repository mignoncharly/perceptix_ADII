"""
Tenant-Aware Historian
Wraps the Historian class to add tenant isolation for incident storage/retrieval.
"""
import logging
from typing import Optional, List

from database import DatabaseManager
from models import IncidentReport
from tenancy.middleware.tenant_resolver import get_current_tenant_id, require_tenant
from tenancy.database.isolation import TenantIsolation
from exceptions import HistorianError


logger = logging.getLogger("TenantHistorian")


class TenantHistorian:
    """
    Tenant-aware version of Historian that automatically filters by tenant_id.

    This wrapper ensures that:
    1. All saved incidents are tagged with the current tenant_id
    2. All queries are automatically filtered by tenant_id
    3. Tenants cannot access each other's incidents
    """

    def __init__(
        self,
        db_manager: DatabaseManager,
        tenant_isolation: Optional[TenantIsolation] = None
    ):
        """
        Initialize tenant-aware historian.

        Args:
            db_manager: Database manager instance
            tenant_isolation: Tenant isolation strategy (defaults to shared schema)
        """
        self.db_manager = db_manager
        self.tenant_isolation = tenant_isolation or TenantIsolation()
        self.component_id = "TENANT_HISTORIAN_V1"
        self.logger = logging.getLogger("TenantHistorian")

    def save_incident(
        self,
        report: IncidentReport,
        tenant_id: Optional[str] = None
    ) -> None:
        """
        Save incident report to database with tenant_id.

        Args:
            report: Validated incident report
            tenant_id: Tenant ID (defaults to current tenant from context)

        Raises:
            HistorianError: If save fails
        """
        try:
            # Get tenant_id from context if not provided
            if tenant_id is None:
                tenant_id = get_current_tenant_id()

            # Save incident with tenant_id
            with self.db_manager.transaction() as conn:
                conn.execute(
                    """INSERT INTO incidents
                       (id, tenant_id, timestamp, type, confidence, summary, full_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        report.report_id,
                        tenant_id,  # Add tenant_id
                        report.timestamp,
                        report.incident_type.value,
                        report.final_confidence_score,
                        report.root_cause_analysis,
                        report.model_dump_json()
                    )
                )
                conn.commit()

            self.logger.info(
                f"[TENANT_HISTORIAN] Incident {report.report_id} archived for tenant {tenant_id}"
            )

        except Exception as e:
            raise HistorianError(
                f"Failed to save incident: {e}",
                component=self.component_id,
                context={"report_id": report.report_id, "tenant_id": tenant_id}
            )

    def get_recent_incidents(
        self,
        limit: int = 10,
        tenant_id: Optional[str] = None
    ) -> List:
        """
        Retrieve recent incidents for current tenant.

        Args:
            limit: Maximum number of incidents to retrieve
            tenant_id: Tenant ID (defaults to current tenant from context)

        Returns:
            List of recent incidents for the tenant

        Raises:
            HistorianError: If retrieval fails
        """
        try:
            # Get tenant_id from context if not provided
            if tenant_id is None:
                tenant_id = get_current_tenant_id()

            with self.db_manager.connection() as conn:
                if tenant_id:
                    # Filter by tenant_id
                    cursor = conn.execute(
                        """SELECT id, timestamp, type, confidence, summary
                           FROM incidents
                           WHERE tenant_id = ?
                           ORDER BY timestamp DESC
                           LIMIT ?""",
                        (tenant_id, limit)
                    )
                else:
                    # No tenant context - return all (admin mode)
                    cursor = conn.execute(
                        """SELECT id, timestamp, type, confidence, summary
                           FROM incidents
                           ORDER BY timestamp DESC
                           LIMIT ?""",
                        (limit,)
                    )

                results = cursor.fetchall()

            self.logger.debug(
                f"[TENANT_HISTORIAN] Retrieved {len(results)} incidents for tenant {tenant_id}"
            )
            return results

        except Exception as e:
            raise HistorianError(
                f"Failed to retrieve incidents: {e}",
                component=self.component_id,
                context={"tenant_id": tenant_id}
            )

    def get_incident_by_id(
        self,
        incident_id: str,
        tenant_id: Optional[str] = None,
        require_tenant_match: bool = True
    ) -> Optional[dict]:
        """
        Retrieve a specific incident by ID.

        Args:
            incident_id: Incident ID to retrieve
            tenant_id: Tenant ID (defaults to current tenant from context)
            require_tenant_match: If True, require incident to belong to tenant

        Returns:
            Incident data or None if not found

        Raises:
            HistorianError: If retrieval fails
        """
        try:
            # Get tenant_id from context if not provided
            if tenant_id is None:
                tenant_id = get_current_tenant_id()

            with self.db_manager.connection() as conn:
                if tenant_id and require_tenant_match:
                    # Filter by both incident_id and tenant_id
                    cursor = conn.execute(
                        """SELECT id, tenant_id, timestamp, type, confidence, summary, full_json
                           FROM incidents
                           WHERE id = ? AND tenant_id = ?""",
                        (incident_id, tenant_id)
                    )
                else:
                    # Admin mode - retrieve without tenant filter
                    cursor = conn.execute(
                        """SELECT id, tenant_id, timestamp, type, confidence, summary, full_json
                           FROM incidents
                           WHERE id = ?""",
                        (incident_id,)
                    )

                row = cursor.fetchone()

            if row:
                return {
                    'id': row[0],
                    'tenant_id': row[1],
                    'timestamp': row[2],
                    'type': row[3],
                    'confidence': row[4],
                    'summary': row[5],
                    'full_json': row[6]
                }

            return None

        except Exception as e:
            raise HistorianError(
                f"Failed to retrieve incident: {e}",
                component=self.component_id,
                context={"incident_id": incident_id, "tenant_id": tenant_id}
            )

    def get_incidents_by_type(
        self,
        incident_type: str,
        limit: int = 100,
        tenant_id: Optional[str] = None
    ) -> List:
        """
        Retrieve incidents by type for current tenant.

        Args:
            incident_type: Incident type to filter by
            limit: Maximum number of incidents to retrieve
            tenant_id: Tenant ID (defaults to current tenant from context)

        Returns:
            List of incidents of the specified type

        Raises:
            HistorianError: If retrieval fails
        """
        try:
            # Get tenant_id from context if not provided
            if tenant_id is None:
                tenant_id = get_current_tenant_id()

            with self.db_manager.connection() as conn:
                if tenant_id:
                    cursor = conn.execute(
                        """SELECT id, timestamp, type, confidence, summary
                           FROM incidents
                           WHERE tenant_id = ? AND type = ?
                           ORDER BY timestamp DESC
                           LIMIT ?""",
                        (tenant_id, incident_type, limit)
                    )
                else:
                    cursor = conn.execute(
                        """SELECT id, timestamp, type, confidence, summary
                           FROM incidents
                           WHERE type = ?
                           ORDER BY timestamp DESC
                           LIMIT ?""",
                        (incident_type, limit)
                    )

                results = cursor.fetchall()

            self.logger.debug(
                f"[TENANT_HISTORIAN] Retrieved {len(results)} incidents of type {incident_type} "
                f"for tenant {tenant_id}"
            )
            return results

        except Exception as e:
            raise HistorianError(
                f"Failed to retrieve incidents by type: {e}",
                component=self.component_id,
                context={"tenant_id": tenant_id, "incident_type": incident_type}
            )

    def get_incident_count(self, tenant_id: Optional[str] = None) -> int:
        """
        Get count of incidents for current tenant.

        Args:
            tenant_id: Tenant ID (defaults to current tenant from context)

        Returns:
            Number of incidents

        Raises:
            HistorianError: If count fails
        """
        try:
            # Get tenant_id from context if not provided
            if tenant_id is None:
                tenant_id = get_current_tenant_id()

            with self.db_manager.connection() as conn:
                if tenant_id:
                    cursor = conn.execute(
                        "SELECT COUNT(*) FROM incidents WHERE tenant_id = ?",
                        (tenant_id,)
                    )
                else:
                    cursor = conn.execute("SELECT COUNT(*) FROM incidents")

                count = cursor.fetchone()[0]

            return count

        except Exception as e:
            raise HistorianError(
                f"Failed to count incidents: {e}",
                component=self.component_id,
                context={"tenant_id": tenant_id}
            )

    def delete_tenant_incidents(
        self,
        tenant_id: str,
        require_current_tenant: bool = True
    ) -> int:
        """
        Delete all incidents for a tenant (admin operation).

        Args:
            tenant_id: Tenant ID to delete incidents for
            require_current_tenant: If True, require tenant_id to match current tenant

        Returns:
            Number of incidents deleted

        Raises:
            HistorianError: If deletion fails
        """
        try:
            # Validate access if required
            if require_current_tenant:
                current_tenant = require_tenant()
                if current_tenant != tenant_id:
                    raise HistorianError(
                        f"Access denied: Cannot delete incidents for tenant {tenant_id}",
                        component=self.component_id,
                        context={"current_tenant": current_tenant, "target_tenant": tenant_id}
                    )

            with self.db_manager.transaction() as conn:
                cursor = conn.execute(
                    "DELETE FROM incidents WHERE tenant_id = ?",
                    (tenant_id,)
                )
                deleted_count = cursor.rowcount
                conn.commit()

            self.logger.warning(
                f"[TENANT_HISTORIAN] Deleted {deleted_count} incidents for tenant {tenant_id}"
            )
            return deleted_count

        except HistorianError:
            raise
        except Exception as e:
            raise HistorianError(
                f"Failed to delete tenant incidents: {e}",
                component=self.component_id,
                context={"tenant_id": tenant_id}
            )
