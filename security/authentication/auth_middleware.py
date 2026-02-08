"""
API Authentication Middleware

FastAPI middleware for JWT authentication.
"""

import logging
from typing import Dict, Optional, Callable
from fastapi import Request, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from security.authentication.jwt_handler import JWTHandler, AuthenticationError
from security.audit.audit_logger import AuditLogger, AuditEventType
from security.rbac.roles import Role, Permission
from security.rbac.permissions import PermissionChecker, PermissionDeniedError


logger = logging.getLogger("AuthMiddleware")

# HTTP Bearer security scheme
security_scheme = HTTPBearer(auto_error=False)


class AuthContext:
    """Authentication context for current request."""

    def __init__(
        self,
        user_id: str,
        roles: list,
        token_payload: Dict,
        ip_address: Optional[str] = None
    ):
        self.user_id = user_id
        self.roles = [Role(r) if isinstance(r, str) else r for r in roles]
        self.token_payload = token_payload
        self.ip_address = ip_address

    @property
    def primary_role(self) -> Role:
        """Get primary (first) role."""
        return self.roles[0] if self.roles else Role.VIEWER

    def has_role(self, role: Role) -> bool:
        """Check if user has role."""
        return role in self.roles

    def has_permission(self, permission: Permission) -> bool:
        """Check if user has permission."""
        from security.rbac.roles import has_permission as check_perm
        return any(check_perm(role, permission) for role in self.roles)


class AuthMiddleware:
    """
    Authentication middleware for FastAPI.

    Supports:
    - JWT Bearer tokens
    - API keys (X-API-Key header)
    - Audit logging
    """

    def __init__(
        self,
        jwt_secret: str,
        audit_logger: Optional[AuditLogger] = None,
        api_keys: Optional[Dict[str, Dict]] = None
    ):
        """
        Initialize authentication middleware.

        Args:
            jwt_secret: JWT secret key
            audit_logger: Optional audit logger
            api_keys: Optional API key mapping
        """
        self.jwt_handler = JWTHandler(jwt_secret)
        self.audit_logger = audit_logger
        self.api_keys = api_keys or {}

    def authenticate_request(
        self,
        request: Request,
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme)
    ) -> AuthContext:
        """
        Authenticate API request.

        Args:
            request: FastAPI request
            credentials: HTTP authorization credentials

        Returns:
            Authentication context

        Raises:
            HTTPException: If authentication fails
        """
        ip_address = request.client.host if request.client else None

        # Try API key first (X-API-Key header)
        api_key = request.headers.get("X-API-Key")
        if api_key:
            return self._authenticate_api_key(api_key, ip_address, request)

        # Try JWT Bearer token
        if credentials:
            return self._authenticate_jwt(credentials.credentials, ip_address, request)

        # No authentication provided
        if self.audit_logger:
            self.audit_logger.log_event(
                event_type=AuditEventType.AUTHENTICATION,
                user="anonymous",
                action="authenticate",
                resource=str(request.url.path),
                status="denied",
                details={"reason": "no_credentials"},
                ip_address=ip_address
            )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"}
        )

    def _authenticate_jwt(
        self,
        token: str,
        ip_address: Optional[str],
        request: Request
    ) -> AuthContext:
        """Authenticate JWT token."""
        try:
            payload = self.jwt_handler.verify_token(token)

            user_id = payload.get('user_id')
            roles = payload.get('roles', [])

            # Log successful authentication
            if self.audit_logger:
                self.audit_logger.log_event(
                    event_type=AuditEventType.AUTHENTICATION,
                    user=user_id,
                    action="authenticate",
                    resource=str(request.url.path),
                    status="success",
                    details={"method": "jwt"},
                    ip_address=ip_address
                )

            return AuthContext(user_id, roles, payload, ip_address)

        except AuthenticationError as e:
            # Log failed authentication
            if self.audit_logger:
                self.audit_logger.log_event(
                    event_type=AuditEventType.AUTHENTICATION,
                    user="unknown",
                    action="authenticate",
                    resource=str(request.url.path),
                    status="failure",
                    details={"error": str(e), "method": "jwt"},
                    ip_address=ip_address
                )

            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(e),
                headers={"WWW-Authenticate": "Bearer"}
            )

    def _authenticate_api_key(
        self,
        api_key: str,
        ip_address: Optional[str],
        request: Request
    ) -> AuthContext:
        """Authenticate API key."""
        if api_key not in self.api_keys:
            # Log failed authentication
            if self.audit_logger:
                self.audit_logger.log_event(
                    event_type=AuditEventType.AUTHENTICATION,
                    user="unknown",
                    action="authenticate",
                    resource=str(request.url.path),
                    status="failure",
                    details={"error": "invalid_api_key", "method": "api_key"},
                    ip_address=ip_address
                )

            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key"
            )

        # Get API key info
        key_info = self.api_keys[api_key]
        user_id = key_info.get('user_id', 'api_client')
        roles = key_info.get('roles', [Role.API_CLIENT.value])

        # Log successful authentication
        if self.audit_logger:
            self.audit_logger.log_event(
                event_type=AuditEventType.AUTHENTICATION,
                user=user_id,
                action="authenticate",
                resource=str(request.url.path),
                status="success",
                details={"method": "api_key"},
                ip_address=ip_address
            )

        return AuthContext(user_id, roles, key_info, ip_address)

    def require_permission(self, permission: Permission) -> Callable:
        """
        Dependency for requiring specific permission.

        Usage:
            @app.get("/admin", dependencies=[Depends(auth.require_permission(Permission.MANAGE_USERS))])
            def admin_endpoint():
                ...
        """
        def check_permission(auth_context: AuthContext = Depends(self.authenticate_request)):
            if not auth_context.has_permission(permission):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission '{permission.value}' required"
                )
            return auth_context

        return check_permission

    def require_role(self, role: Role) -> Callable:
        """
        Dependency for requiring specific role.

        Usage:
            @app.get("/admin", dependencies=[Depends(auth.require_role(Role.ADMIN))])
            def admin_endpoint():
                ...
        """
        def check_role(auth_context: AuthContext = Depends(self.authenticate_request)):
            if not auth_context.has_role(role):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Role '{role.value}' required"
                )
            return auth_context

        return check_role


def get_auth_context(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme)
) -> Optional[AuthContext]:
    """
    Get authentication context (if available) without requiring authentication.

    This is useful for optional authentication.

    Args:
        request: FastAPI request
        credentials: HTTP authorization credentials

    Returns:
        AuthContext if authenticated, None otherwise
    """
    # This would need access to AuthMiddleware instance
    # For now, return None
    return None
