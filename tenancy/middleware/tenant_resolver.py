"""
Tenant Resolver Middleware
Resolves tenant from HTTP request and sets tenant context.
"""
import logging
from typing import Optional, Dict, Any, Callable
from contextvars import ContextVar
from dataclasses import dataclass
from urllib.parse import urlparse

from tenancy.tenant_manager import TenantManager
from exceptions import PerceptixError


logger = logging.getLogger("TenantResolver")


# Context variable for storing current tenant ID
_tenant_context: ContextVar[Optional[str]] = ContextVar('tenant_context', default=None)


class TenantResolutionError(PerceptixError):
    """Raised when tenant cannot be resolved."""
    pass


class InvalidTenantError(PerceptixError):
    """Raised when tenant is invalid or not found."""
    pass


@dataclass
class TenantContext:
    """
    Represents the tenant context for a request.
    """
    tenant_id: str
    tenant_name: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TenantContext':
        """Create TenantContext from dictionary."""
        return cls(
            tenant_id=data['tenant_id'],
            tenant_name=data.get('tenant_name'),
            metadata=data.get('metadata')
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'tenant_id': self.tenant_id,
            'tenant_name': self.tenant_name,
            'metadata': self.metadata
        }


class TenantResolver:
    """
    Resolves tenant from HTTP request.
    Supports multiple resolution strategies:
    1. X-Tenant-ID header
    2. Subdomain (tenant.cognizant.com)
    3. API key prefix (tenant:key)
    4. JWT claim
    """

    def __init__(
        self,
        tenant_manager: TenantManager,
        require_tenant: bool = True,
        default_tenant: Optional[str] = None
    ):
        """
        Initialize tenant resolver.

        Args:
            tenant_manager: TenantManager instance
            require_tenant: If True, require tenant to be present (raise error if not found)
            default_tenant: Default tenant ID to use if none resolved
        """
        self.tenant_manager = tenant_manager
        self.require_tenant = require_tenant
        self.default_tenant = default_tenant
        self.logger = logging.getLogger("TenantResolver")

    def resolve_tenant(self, request: Any) -> Optional[str]:
        """
        Resolve tenant ID from HTTP request.

        Resolution order:
        1. X-Tenant-ID header
        2. Subdomain (tenant.example.com)
        3. API key prefix (tenant:key)
        4. JWT claim (tenant_id)
        5. Default tenant (if configured)

        Args:
            request: HTTP request object (FastAPI Request or similar)

        Returns:
            Tenant ID or None if not resolved

        Raises:
            TenantResolutionError: If tenant required but not found
            InvalidTenantError: If tenant ID is invalid or tenant doesn't exist
        """
        tenant_id = None

        # Strategy 1: X-Tenant-ID header
        if hasattr(request, 'headers'):
            tenant_id = request.headers.get('X-Tenant-ID') or request.headers.get('x-tenant-id')
            if tenant_id:
                self.logger.debug(f"Resolved tenant from X-Tenant-ID header: {tenant_id}")
                return self._validate_tenant(tenant_id)

        # Strategy 2: Subdomain
        if hasattr(request, 'url'):
            tenant_id = self._resolve_from_subdomain(str(request.url))
            if tenant_id:
                self.logger.debug(f"Resolved tenant from subdomain: {tenant_id}")
                return self._validate_tenant(tenant_id)

        # Strategy 3: API key prefix
        if hasattr(request, 'headers'):
            api_key = request.headers.get('Authorization') or request.headers.get('X-API-Key')
            if api_key:
                tenant_id = self._resolve_from_api_key(api_key)
                if tenant_id:
                    self.logger.debug(f"Resolved tenant from API key: {tenant_id}")
                    return self._validate_tenant(tenant_id)

        # Strategy 4: JWT claim (from request user context)
        # Starlette's Request.user property asserts unless AuthenticationMiddleware is installed,
        # so we must avoid touching request.user unless it is present in scope.
        scope = getattr(request, "scope", None)
        if isinstance(scope, dict) and "user" in scope:
            user = scope.get("user")
            tenant_id = getattr(user, "tenant_id", None)
            if tenant_id:
                self.logger.debug(f"Resolved tenant from JWT claim: {tenant_id}")
                return self._validate_tenant(str(tenant_id))

        # Strategy 5: Default tenant
        if self.default_tenant:
            self.logger.debug(f"Using default tenant: {self.default_tenant}")
            return self._validate_tenant(self.default_tenant)

        # No tenant resolved
        if self.require_tenant:
            raise TenantResolutionError(
                "Tenant ID is required but could not be resolved from request. "
                "Please provide X-Tenant-ID header or configure tenant resolution."
            )

        return None

    def _resolve_from_subdomain(self, url: str) -> Optional[str]:
        """
        Extract tenant ID from subdomain.

        Examples:
            - acme.cognizant.com -> acme
            - tenant-123.example.com -> tenant-123
            - www.example.com -> None (www is not a tenant)

        Args:
            url: Full URL string

        Returns:
            Tenant ID or None
        """
        try:
            parsed = urlparse(url)
            hostname = parsed.hostname or ""
            parts = hostname.split('.')

            # Need at least 3 parts (subdomain.domain.tld)
            if len(parts) < 3:
                return None

            # First part is potential tenant
            subdomain = parts[0]

            # Skip common non-tenant subdomains
            if subdomain.lower() in ['www', 'api', 'app', 'admin', 'portal', 'dashboard']:
                return None

            # Validate format (alphanumeric and hyphens)
            if not subdomain.replace('-', '').isalnum():
                return None

            return subdomain

        except Exception as e:
            self.logger.warning(f"Failed to parse subdomain from URL: {url}: {e}")
            return None

    def _resolve_from_api_key(self, api_key: str) -> Optional[str]:
        """
        Extract tenant ID from API key prefix.

        Expected format: tenant-id:actual-key
        Example: acme:sk_live_abc123 -> acme

        Args:
            api_key: API key string (may include "Bearer " prefix)

        Returns:
            Tenant ID or None
        """
        try:
            # Remove "Bearer " prefix if present
            if api_key.startswith('Bearer '):
                api_key = api_key[7:]

            # Check if key has tenant prefix (format: tenant:key)
            if ':' in api_key:
                tenant_id = api_key.split(':', 1)[0]
                # Validate format
                if tenant_id.replace('-', '').isalnum():
                    return tenant_id

            return None

        except Exception as e:
            self.logger.warning(f"Failed to parse tenant from API key: {e}")
            return None

    def _validate_tenant(self, tenant_id: str) -> str:
        """
        Validate that tenant exists and is active.

        Args:
            tenant_id: Tenant ID to validate

        Returns:
            Validated tenant ID

        Raises:
            InvalidTenantError: If tenant doesn't exist or is not active
        """
        tenant = self.tenant_manager.get_tenant(tenant_id)

        if not tenant:
            raise InvalidTenantError(f"Tenant not found: {tenant_id}")

        if not tenant.is_active():
            raise InvalidTenantError(
                f"Tenant is not active: {tenant_id} (status: {tenant.status.value})"
            )

        return tenant_id

    def set_tenant_context(self, tenant_id: str) -> None:
        """
        Set tenant context for current request.

        Args:
            tenant_id: Tenant ID to set in context
        """
        _tenant_context.set(tenant_id)
        self.logger.debug(f"Set tenant context: {tenant_id}")

    def clear_tenant_context(self) -> None:
        """Clear tenant context."""
        _tenant_context.set(None)
        self.logger.debug("Cleared tenant context")

    def get_current_tenant(self) -> Optional[str]:
        """
        Get current tenant ID from context.

        Returns:
            Current tenant ID or None
        """
        return _tenant_context.get()

    def get_current_tenant_context(self) -> Optional[TenantContext]:
        """
        Get full tenant context for current request.

        Returns:
            TenantContext object or None
        """
        tenant_id = self.get_current_tenant()
        if not tenant_id:
            return None

        tenant = self.tenant_manager.get_tenant(tenant_id)
        if not tenant:
            return None

        return TenantContext(
            tenant_id=tenant.id,
            tenant_name=tenant.name,
            metadata=tenant.metadata
        )

    def middleware(self, request_handler: Callable) -> Callable:
        """
        Create middleware function that resolves tenant and sets context.

        Usage with FastAPI:
            @app.middleware("http")
            async def tenant_middleware(request: Request, call_next):
                return await tenant_resolver.middleware(call_next)(request)

        Args:
            request_handler: Next request handler in chain

        Returns:
            Middleware function
        """
        async def _middleware(request: Any):
            """Middleware function that resolves tenant."""
            try:
                # Resolve tenant from request
                tenant_id = self.resolve_tenant(request)

                # Set tenant context
                if tenant_id:
                    self.set_tenant_context(tenant_id)
                    self.logger.info(f"Processing request for tenant: {tenant_id}")

                # Call next handler
                response = await request_handler(request)

                return response

            except (TenantResolutionError, InvalidTenantError) as e:
                # Log and re-raise tenant errors
                self.logger.error(f"Tenant resolution failed: {e}")
                raise

            finally:
                # Always clear context after request
                self.clear_tenant_context()

        return _middleware


def get_current_tenant_id() -> Optional[str]:
    """
    Get current tenant ID from context (convenience function).

    Returns:
        Current tenant ID or None
    """
    return _tenant_context.get()


def require_tenant() -> str:
    """
    Get current tenant ID or raise error if not set.

    Returns:
        Current tenant ID

    Raises:
        TenantResolutionError: If no tenant in context
    """
    tenant_id = _tenant_context.get()
    if not tenant_id:
        raise TenantResolutionError("No tenant context set for this request")
    return tenant_id
