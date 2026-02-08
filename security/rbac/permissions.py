"""
Permission Checker

Runtime permission checking and enforcement.
"""

import logging
from typing import List, Optional
from security.rbac.roles import Role, Permission, has_permission


logger = logging.getLogger("PermissionChecker")


class PermissionDeniedError(Exception):
    """Permission denied error."""
    pass


class PermissionChecker:
    """
    Runtime permission checking.

    Provides decorators and functions for permission enforcement.
    """

    @staticmethod
    def check_permission(
        user_role: Role,
        required_permission: Permission,
        raise_on_deny: bool = True
    ) -> bool:
        """
        Check if user has permission.

        Args:
            user_role: User's role
            required_permission: Required permission
            raise_on_deny: Raise exception if denied

        Returns:
            True if permitted

        Raises:
            PermissionDeniedError: If permission denied and raise_on_deny is True
        """
        has_perm = has_permission(user_role, required_permission)

        if not has_perm:
            logger.warning(
                f"Permission denied: {user_role.value} attempted {required_permission.value}"
            )

            if raise_on_deny:
                raise PermissionDeniedError(
                    f"Role '{user_role.value}' does not have permission '{required_permission.value}'"
                )

        return has_perm

    @staticmethod
    def check_any_permission(
        user_role: Role,
        required_permissions: List[Permission],
        raise_on_deny: bool = True
    ) -> bool:
        """
        Check if user has any of the permissions.

        Args:
            user_role: User's role
            required_permissions: List of permissions (any will do)
            raise_on_deny: Raise exception if denied

        Returns:
            True if user has at least one permission

        Raises:
            PermissionDeniedError: If no permissions and raise_on_deny is True
        """
        for perm in required_permissions:
            if has_permission(user_role, perm):
                return True

        if raise_on_deny:
            perm_names = [p.value for p in required_permissions]
            raise PermissionDeniedError(
                f"Role '{user_role.value}' does not have any of: {', '.join(perm_names)}"
            )

        return False

    @staticmethod
    def check_all_permissions(
        user_role: Role,
        required_permissions: List[Permission],
        raise_on_deny: bool = True
    ) -> bool:
        """
        Check if user has all of the permissions.

        Args:
            user_role: User's role
            required_permissions: List of permissions (all required)
            raise_on_deny: Raise exception if denied

        Returns:
            True if user has all permissions

        Raises:
            PermissionDeniedError: If missing permissions and raise_on_deny is True
        """
        missing = []
        for perm in required_permissions:
            if not has_permission(user_role, perm):
                missing.append(perm)

        if missing:
            if raise_on_deny:
                perm_names = [p.value for p in missing]
                raise PermissionDeniedError(
                    f"Role '{user_role.value}' is missing permissions: {', '.join(perm_names)}"
                )
            return False

        return True

    @staticmethod
    def require_permission(required_permission: Permission):
        """
        Decorator to enforce permission on functions.

        Args:
            required_permission: Required permission

        Usage:
            @require_permission(Permission.TRIGGER_CYCLES)
            def trigger_cycle(user_role: Role):
                # Function code
        """
        def decorator(func):
            def wrapper(*args, **kwargs):
                # Try to extract user_role from args or kwargs
                user_role = None

                # Check kwargs first
                if 'user_role' in kwargs:
                    user_role = kwargs['user_role']
                # Check first arg
                elif len(args) > 0 and isinstance(args[0], Role):
                    user_role = args[0]

                if user_role is None:
                    raise PermissionDeniedError(
                        "Cannot determine user role for permission check"
                    )

                # Check permission
                PermissionChecker.check_permission(user_role, required_permission)

                # Execute function
                return func(*args, **kwargs)

            wrapper.__name__ = func.__name__
            wrapper.__doc__ = func.__doc__
            return wrapper

        return decorator

    @staticmethod
    def is_admin(user_role: Role) -> bool:
        """Check if user is admin."""
        return user_role == Role.ADMIN

    @staticmethod
    def can_modify_config(user_role: Role) -> bool:
        """Check if user can modify configuration."""
        return has_permission(user_role, Permission.MODIFY_CONFIG)

    @staticmethod
    def can_trigger_cycles(user_role: Role) -> bool:
        """Check if user can trigger monitoring cycles."""
        return has_permission(user_role, Permission.TRIGGER_CYCLES)

    @staticmethod
    def can_execute_remediation(user_role: Role) -> bool:
        """Check if user can execute remediation."""
        return has_permission(user_role, Permission.EXECUTE_REMEDIATION)

    @staticmethod
    def can_manage_users(user_role: Role) -> bool:
        """Check if user can manage users."""
        return has_permission(user_role, Permission.MANAGE_USERS)
