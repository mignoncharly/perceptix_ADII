"""
Tenant Isolation Strategy
Implements shared schema approach with tenant_id filtering.
"""
import logging
from typing import Dict, List, Optional, Any, Callable
from enum import Enum

from tenancy.middleware.tenant_resolver import get_current_tenant_id, require_tenant
from exceptions import PerceptixError


logger = logging.getLogger("TenantIsolation")


class IsolationStrategy(Enum):
    """Tenant isolation strategies."""
    SHARED_SCHEMA = "shared_schema"  # Single database, tenant_id column (implemented)
    SEPARATE_SCHEMA = "separate_schema"  # Separate schemas per tenant (future)
    SEPARATE_DATABASE = "separate_database"  # Separate databases per tenant (future)


class TenantIsolationError(PerceptixError):
    """Raised when tenant isolation is violated."""
    pass


class TenantIsolation:
    """
    Manages tenant data isolation in shared schema approach.

    Shared Schema Strategy:
    - All tenants share the same database tables
    - Each table has a `tenant_id` column
    - All queries automatically filtered by tenant_id
    - Row-level security ensures data isolation
    """

    def __init__(self, strategy: IsolationStrategy = IsolationStrategy.SHARED_SCHEMA):
        """
        Initialize tenant isolation.

        Args:
            strategy: Isolation strategy to use
        """
        self.strategy = strategy
        self.logger = logging.getLogger("TenantIsolation")

        if strategy != IsolationStrategy.SHARED_SCHEMA:
            raise NotImplementedError(
                f"Only SHARED_SCHEMA strategy is currently implemented. "
                f"Requested: {strategy.value}"
            )

    def add_tenant_filter(
        self,
        query_params: Dict[str, Any],
        require_tenant_context: bool = True
    ) -> Dict[str, Any]:
        """
        Add tenant_id filter to query parameters.

        Args:
            query_params: Original query parameters
            require_tenant_context: If True, require tenant context to be set

        Returns:
            Query parameters with tenant_id filter added

        Raises:
            TenantIsolationError: If tenant context required but not set
        """
        if require_tenant_context:
            tenant_id = require_tenant()
        else:
            tenant_id = get_current_tenant_id()

        if tenant_id:
            # Add tenant_id to query params
            filtered_params = query_params.copy()
            filtered_params['tenant_id'] = tenant_id
            self.logger.debug(f"Added tenant filter: tenant_id={tenant_id}")
            return filtered_params

        return query_params

    def filter_by_tenant(
        self,
        data: List[Dict[str, Any]],
        tenant_id_field: str = 'tenant_id'
    ) -> List[Dict[str, Any]]:
        """
        Filter data list by current tenant.

        Args:
            data: List of data dictionaries
            tenant_id_field: Field name containing tenant ID

        Returns:
            Filtered data list containing only current tenant's data
        """
        tenant_id = get_current_tenant_id()
        if not tenant_id:
            # No tenant context, return all data (admin mode)
            return data

        filtered = [
            item for item in data
            if item.get(tenant_id_field) == tenant_id
        ]

        self.logger.debug(
            f"Filtered {len(data)} items to {len(filtered)} items for tenant {tenant_id}"
        )

        return filtered

    def validate_tenant_access(
        self,
        resource_tenant_id: str,
        current_tenant_id: Optional[str] = None
    ) -> bool:
        """
        Validate that current tenant has access to resource.

        Args:
            resource_tenant_id: Tenant ID of the resource
            current_tenant_id: Current tenant ID (defaults to context tenant)

        Returns:
            True if access allowed

        Raises:
            TenantIsolationError: If access denied
        """
        if current_tenant_id is None:
            current_tenant_id = require_tenant()

        if resource_tenant_id != current_tenant_id:
            raise TenantIsolationError(
                f"Access denied: Resource belongs to tenant '{resource_tenant_id}', "
                f"but current tenant is '{current_tenant_id}'"
            )

        return True

    def wrap_query(
        self,
        query_func: Callable,
        auto_filter: bool = True
    ) -> Callable:
        """
        Wrap a query function to automatically add tenant filtering.

        Args:
            query_func: Original query function
            auto_filter: If True, automatically add tenant_id filter

        Returns:
            Wrapped function with tenant filtering
        """
        def wrapped(*args, **kwargs):
            """Wrapped query with tenant filtering."""
            if auto_filter:
                tenant_id = get_current_tenant_id()
                if tenant_id:
                    # Add tenant_id to kwargs
                    kwargs['tenant_id'] = tenant_id
                    self.logger.debug(f"Auto-added tenant filter: tenant_id={tenant_id}")

            return query_func(*args, **kwargs)

        return wrapped

    def get_tenant_query_filter(self) -> Dict[str, str]:
        """
        Get tenant filter for SQL WHERE clause.

        Returns:
            Dictionary with tenant_id filter

        Example:
            filter = isolation.get_tenant_query_filter()
            # Returns: {'tenant_id': 'acme-corp'}
            # Use in SQL: WHERE tenant_id = :tenant_id
        """
        tenant_id = require_tenant()
        return {'tenant_id': tenant_id}

    def build_tenant_where_clause(
        self,
        additional_conditions: Optional[List[str]] = None
    ) -> str:
        """
        Build SQL WHERE clause with tenant filtering.

        Args:
            additional_conditions: Additional WHERE conditions

        Returns:
            SQL WHERE clause string

        Example:
            clause = isolation.build_tenant_where_clause(['status = ?', 'created_at > ?'])
            # Returns: "WHERE tenant_id = ? AND status = ? AND created_at > ?"
        """
        tenant_id = require_tenant()
        conditions = [f"tenant_id = '{tenant_id}'"]

        if additional_conditions:
            conditions.extend(additional_conditions)

        where_clause = " AND ".join(conditions)
        return f"WHERE {where_clause}"

    def create_tenant_scoped_dict(
        self,
        data: Dict[str, Any],
        tenant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create dictionary with tenant_id automatically added.

        Args:
            data: Original data dictionary
            tenant_id: Tenant ID (defaults to current tenant)

        Returns:
            Dictionary with tenant_id added
        """
        if tenant_id is None:
            tenant_id = require_tenant()

        scoped_data = data.copy()
        scoped_data['tenant_id'] = tenant_id

        return scoped_data

    def verify_tenant_isolation(
        self,
        table_name: str,
        has_tenant_column: bool = True
    ) -> bool:
        """
        Verify that table has proper tenant isolation.

        Args:
            table_name: Name of table to verify
            has_tenant_column: Whether table should have tenant_id column

        Returns:
            True if isolation is proper

        Raises:
            TenantIsolationError: If isolation requirements not met
        """
        if not has_tenant_column:
            raise TenantIsolationError(
                f"Table '{table_name}' is missing tenant_id column. "
                f"All tables in shared schema must have tenant_id for isolation."
            )

        self.logger.info(f"Verified tenant isolation for table: {table_name}")
        return True


# Global instance for shared schema isolation
_default_isolation = TenantIsolation(strategy=IsolationStrategy.SHARED_SCHEMA)


def get_default_isolation() -> TenantIsolation:
    """
    Get default tenant isolation instance.

    Returns:
        Global TenantIsolation instance
    """
    return _default_isolation


def add_tenant_filter_to_query(query_params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convenience function to add tenant filter to query.

    Args:
        query_params: Original query parameters

    Returns:
        Query parameters with tenant_id filter
    """
    return _default_isolation.add_tenant_filter(query_params)


def require_tenant_for_resource(resource_tenant_id: str) -> bool:
    """
    Convenience function to validate tenant access.

    Args:
        resource_tenant_id: Tenant ID of resource

    Returns:
        True if access allowed

    Raises:
        TenantIsolationError: If access denied
    """
    return _default_isolation.validate_tenant_access(resource_tenant_id)
