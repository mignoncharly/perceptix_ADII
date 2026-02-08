"""
Tenant Manager - CRUD operations for tenants
Manages tenant lifecycle and configuration.
"""
import logging
import sqlite3
from typing import Dict, List, Optional
from datetime import datetime
from pathlib import Path

from tenancy.models.tenant import (
    Tenant, TenantConfig, TenantStatus,
    TenantCreate, TenantUpdate
)
from exceptions import PerceptixError


logger = logging.getLogger("TenantManager")


class TenantError(PerceptixError):
    """Base class for tenant-related errors."""
    pass


class TenantNotFoundError(TenantError):
    """Raised when tenant is not found."""
    pass


class TenantAlreadyExistsError(TenantError):
    """Raised when trying to create a tenant that already exists."""
    pass


class TenantManager:
    """
    Manages tenant CRUD operations and lifecycle.
    """

    def __init__(self, db_path: str = "cognizant_tenants.db"):
        """
        Initialize tenant manager.

        Args:
            db_path: Path to tenant database
        """
        self.db_path = db_path
        self.logger = logging.getLogger("TenantManager")
        self._init_database()

    def _init_database(self):
        """Initialize tenant database with schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Create tenants table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tenants (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                config TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                updated_at TEXT,
                metadata TEXT
            )
        """)

        conn.commit()
        conn.close()

        self.logger.info(f"Tenant database initialized: {self.db_path}")

    def create_tenant(
        self,
        tenant_create: TenantCreate
    ) -> Tenant:
        """
        Create a new tenant.

        Args:
            tenant_create: Tenant creation request

        Returns:
            Created tenant

        Raises:
            TenantAlreadyExistsError: If tenant already exists
        """
        # Check if tenant exists
        if self.get_tenant(tenant_create.id):
            raise TenantAlreadyExistsError(f"Tenant already exists: {tenant_create.id}")

        # Create tenant
        tenant = Tenant(
            id=tenant_create.id,
            name=tenant_create.name,
            config=tenant_create.config or TenantConfig(),
            status=TenantStatus.ACTIVE,
            created_at=datetime.now(),
            metadata=tenant_create.metadata
        )

        # Save to database
        import json
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO tenants (id, name, config, status, created_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            tenant.id,
            tenant.name,
            json.dumps(tenant.config.model_dump()),
            tenant.status.value,
            tenant.created_at.isoformat(),
            json.dumps(tenant.metadata)
        ))

        conn.commit()
        conn.close()

        self.logger.info(f"Created tenant: {tenant.id}")

        return tenant

    def get_tenant(self, tenant_id: str) -> Optional[Tenant]:
        """
        Get a tenant by ID.

        Args:
            tenant_id: Tenant ID

        Returns:
            Tenant or None if not found
        """
        import json
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, name, config, status, created_at, updated_at, metadata
            FROM tenants
            WHERE id = ?
        """, (tenant_id,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        # Parse row data
        tenant = Tenant(
            id=row[0],
            name=row[1],
            config=TenantConfig(**json.loads(row[2])),
            status=TenantStatus(row[3]),
            created_at=datetime.fromisoformat(row[4]),
            updated_at=datetime.fromisoformat(row[5]) if row[5] else None,
            metadata=json.loads(row[6]) if row[6] else {}
        )

        return tenant

    def list_tenants(
        self,
        status: Optional[TenantStatus] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Tenant]:
        """
        List tenants.

        Args:
            status: Filter by status (None for all)
            limit: Maximum number of tenants to return
            offset: Offset for pagination

        Returns:
            List of tenants
        """
        import json
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if status:
            cursor.execute("""
                SELECT id, name, config, status, created_at, updated_at, metadata
                FROM tenants
                WHERE status = ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            """, (status.value, limit, offset))
        else:
            cursor.execute("""
                SELECT id, name, config, status, created_at, updated_at, metadata
                FROM tenants
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            """, (limit, offset))

        rows = cursor.fetchall()
        conn.close()

        tenants = []
        for row in rows:
            tenant = Tenant(
                id=row[0],
                name=row[1],
                config=TenantConfig(**json.loads(row[2])),
                status=TenantStatus(row[3]),
                created_at=datetime.fromisoformat(row[4]),
                updated_at=datetime.fromisoformat(row[5]) if row[5] else None,
                metadata=json.loads(row[6]) if row[6] else {}
            )
            tenants.append(tenant)

        return tenants

    def update_tenant(
        self,
        tenant_id: str,
        tenant_update: TenantUpdate
    ) -> Tenant:
        """
        Update a tenant.

        Args:
            tenant_id: Tenant ID to update
            tenant_update: Update request

        Returns:
            Updated tenant

        Raises:
            TenantNotFoundError: If tenant not found
        """
        # Get existing tenant
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            raise TenantNotFoundError(f"Tenant not found: {tenant_id}")

        # Apply updates
        if tenant_update.name is not None:
            tenant.name = tenant_update.name
        if tenant_update.config is not None:
            tenant.config = tenant_update.config
        if tenant_update.status is not None:
            tenant.status = tenant_update.status
        if tenant_update.metadata is not None:
            tenant.metadata = tenant_update.metadata

        tenant.updated_at = datetime.now()

        # Save to database
        import json
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE tenants
            SET name = ?, config = ?, status = ?, updated_at = ?, metadata = ?
            WHERE id = ?
        """, (
            tenant.name,
            json.dumps(tenant.config.model_dump()),
            tenant.status.value,
            tenant.updated_at.isoformat(),
            json.dumps(tenant.metadata),
            tenant_id
        ))

        conn.commit()
        conn.close()

        self.logger.info(f"Updated tenant: {tenant_id}")

        return tenant

    def delete_tenant(self, tenant_id: str, hard_delete: bool = False) -> bool:
        """
        Delete a tenant.

        Args:
            tenant_id: Tenant ID to delete
            hard_delete: If True, permanently delete. If False, soft delete (mark inactive)

        Returns:
            True if deleted successfully

        Raises:
            TenantNotFoundError: If tenant not found
        """
        # Check if tenant exists
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            raise TenantNotFoundError(f"Tenant not found: {tenant_id}")

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if hard_delete:
            # Permanently delete
            cursor.execute("DELETE FROM tenants WHERE id = ?", (tenant_id,))
            self.logger.warning(f"Hard deleted tenant: {tenant_id}")
        else:
            # Soft delete (mark as inactive)
            cursor.execute("""
                UPDATE tenants
                SET status = ?, updated_at = ?
                WHERE id = ?
            """, (TenantStatus.INACTIVE.value, datetime.now().isoformat(), tenant_id))
            self.logger.info(f"Soft deleted tenant: {tenant_id}")

        conn.commit()
        conn.close()

        return True

    def get_tenant_count(self, status: Optional[TenantStatus] = None) -> int:
        """
        Get count of tenants.

        Args:
            status: Filter by status (None for all)

        Returns:
            Number of tenants
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if status:
            cursor.execute("SELECT COUNT(*) FROM tenants WHERE status = ?", (status.value,))
        else:
            cursor.execute("SELECT COUNT(*) FROM tenants")

        count = cursor.fetchone()[0]
        conn.close()

        return count

    def tenant_exists(self, tenant_id: str) -> bool:
        """
        Check if a tenant exists.

        Args:
            tenant_id: Tenant ID

        Returns:
            True if tenant exists
        """
        return self.get_tenant(tenant_id) is not None
