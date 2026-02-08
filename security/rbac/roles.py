"""
Role-Based Access Control (RBAC)

Role and permission definitions.
"""

from enum import Enum
from typing import List


class Role(str, Enum):
    """System roles."""
    ADMIN = "admin"              # Full access to all features
    OPERATOR = "operator"        # View incidents, trigger cycles, execute remediation
    VIEWER = "viewer"            # Read-only access
    API_CLIENT = "api_client"    # Programmatic access for integrations
    ANALYST = "analyst"          # View and investigate incidents


class Permission(str, Enum):
    """System permissions."""
    # Incident management
    VIEW_INCIDENTS = "view_incidents"
    CREATE_INCIDENTS = "create_incidents"
    ACKNOWLEDGE_INCIDENTS = "acknowledge_incidents"
    CLOSE_INCIDENTS = "close_incidents"

    # Monitoring
    TRIGGER_CYCLES = "trigger_cycles"
    VIEW_METRICS = "view_metrics"
    VIEW_SYSTEM_STATUS = "view_system_status"

    # Configuration
    MODIFY_CONFIG = "modify_config"
    VIEW_CONFIG = "view_config"
    MANAGE_RULES = "manage_rules"
    MANAGE_DATASOURCES = "manage_datasources"

    # Security
    MANAGE_USERS = "manage_users"
    MANAGE_ROLES = "manage_roles"
    VIEW_AUDIT_LOG = "view_audit_log"
    MANAGE_SECRETS = "manage_secrets"

    # Remediation
    EXECUTE_REMEDIATION = "execute_remediation"
    APPROVE_REMEDIATION = "approve_remediation"

    # API access
    API_ACCESS = "api_access"
    WEBHOOK_ACCESS = "webhook_access"

    # System administration
    MANAGE_TENANTS = "manage_tenants"
    SYSTEM_SHUTDOWN = "system_shutdown"
    VIEW_LOGS = "view_logs"


# Role-to-permissions mapping
ROLE_PERMISSIONS = {
    Role.ADMIN: [perm for perm in Permission],  # All permissions

    Role.OPERATOR: [
        Permission.VIEW_INCIDENTS,
        Permission.ACKNOWLEDGE_INCIDENTS,
        Permission.TRIGGER_CYCLES,
        Permission.VIEW_METRICS,
        Permission.VIEW_SYSTEM_STATUS,
        Permission.VIEW_CONFIG,
        Permission.EXECUTE_REMEDIATION,
        Permission.API_ACCESS,
        Permission.VIEW_LOGS
    ],

    Role.VIEWER: [
        Permission.VIEW_INCIDENTS,
        Permission.VIEW_METRICS,
        Permission.VIEW_SYSTEM_STATUS,
        Permission.VIEW_CONFIG,
        Permission.VIEW_LOGS
    ],

    Role.API_CLIENT: [
        Permission.VIEW_INCIDENTS,
        Permission.CREATE_INCIDENTS,
        Permission.TRIGGER_CYCLES,
        Permission.VIEW_METRICS,
        Permission.VIEW_SYSTEM_STATUS,
        Permission.API_ACCESS,
        Permission.WEBHOOK_ACCESS
    ],

    Role.ANALYST: [
        Permission.VIEW_INCIDENTS,
        Permission.ACKNOWLEDGE_INCIDENTS,
        Permission.VIEW_METRICS,
        Permission.VIEW_SYSTEM_STATUS,
        Permission.VIEW_CONFIG,
        Permission.VIEW_AUDIT_LOG,
        Permission.VIEW_LOGS
    ]
}


def has_permission(user_role: Role, permission: Permission) -> bool:
    """
    Check if a role has a specific permission.

    Args:
        user_role: User's role
        permission: Permission to check

    Returns:
        True if role has permission
    """
    return permission in ROLE_PERMISSIONS.get(user_role, [])


def has_any_permission(user_role: Role, permissions: List[Permission]) -> bool:
    """
    Check if role has any of the specified permissions.

    Args:
        user_role: User's role
        permissions: List of permissions

    Returns:
        True if role has at least one permission
    """
    role_perms = ROLE_PERMISSIONS.get(user_role, [])
    return any(perm in role_perms for perm in permissions)


def has_all_permissions(user_role: Role, permissions: List[Permission]) -> bool:
    """
    Check if role has all of the specified permissions.

    Args:
        user_role: User's role
        permissions: List of permissions

    Returns:
        True if role has all permissions
    """
    role_perms = ROLE_PERMISSIONS.get(user_role, [])
    return all(perm in role_perms for perm in permissions)


def get_role_permissions(user_role: Role) -> List[Permission]:
    """
    Get all permissions for a role.

    Args:
        user_role: User's role

    Returns:
        List of permissions
    """
    return ROLE_PERMISSIONS.get(user_role, [])


def get_roles_with_permission(permission: Permission) -> List[Role]:
    """
    Get all roles that have a specific permission.

    Args:
        permission: Permission to check

    Returns:
        List of roles
    """
    roles = []
    for role, perms in ROLE_PERMISSIONS.items():
        if permission in perms:
            roles.append(role)
    return roles
