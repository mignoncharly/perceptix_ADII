"""Authentication module."""

from security.authentication.jwt_handler import JWTHandler, AuthenticationError

__all__ = ['JWTHandler', 'AuthenticationError']
