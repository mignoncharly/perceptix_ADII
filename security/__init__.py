"""
Cognizant Security Module

Provides comprehensive security features including:
- Audit logging
- Secrets encryption
- JWT authentication
- Role-based access control (RBAC)
- Security scanning
"""

from security.audit.audit_logger import AuditLogger, AuditEventType
from security.audit.audit_models import AuditEvent
from security.encryption.secrets_manager import SecretsManager
from security.authentication.jwt_handler import JWTHandler, AuthenticationError
from security.rbac.roles import Role, Permission, has_permission

__all__ = [
    'AuditLogger',
    'AuditEventType',
    'AuditEvent',
    'SecretsManager',
    'JWTHandler',
    'AuthenticationError',
    'Role',
    'Permission',
    'has_permission'
]
