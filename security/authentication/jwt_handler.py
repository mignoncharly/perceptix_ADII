"""
JWT Authentication Handler

JWT token generation and validation.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import jwt


logger = logging.getLogger("JWTHandler")


class AuthenticationError(Exception):
    """Authentication error."""
    pass


class JWTHandler:
    """
    JWT token generation and validation.

    Features:
    - HS256 algorithm (HMAC with SHA-256)
    - Token expiration
    - Role-based claims
    - Refresh token support
    """

    def __init__(self, secret_key: str, algorithm: str = "HS256"):
        """
        Initialize JWT handler.

        Args:
            secret_key: Secret key for signing tokens
            algorithm: JWT algorithm (default: HS256)
        """
        self.secret_key = secret_key
        self.algorithm = algorithm

        logger.info("JWT handler initialized")

    def generate_token(
        self,
        user_id: str,
        roles: List[str],
        expiry_hours: int = 24,
        additional_claims: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Generate JWT access token.

        Args:
            user_id: User identifier
            roles: List of user roles
            expiry_hours: Token expiry in hours
            additional_claims: Additional claims to include

        Returns:
            JWT token string
        """
        now = datetime.utcnow()
        exp = now + timedelta(hours=expiry_hours)

        payload = {
            'user_id': user_id,
            'roles': roles,
            'exp': exp,
            'iat': now,
            'nbf': now,  # Not valid before
            'type': 'access'
        }

        # Add additional claims
        if additional_claims:
            payload.update(additional_claims)

        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

        logger.info(f"Generated access token for user {user_id}")

        return token

    def generate_refresh_token(
        self,
        user_id: str,
        expiry_days: int = 30
    ) -> str:
        """
        Generate JWT refresh token.

        Args:
            user_id: User identifier
            expiry_days: Token expiry in days

        Returns:
            JWT refresh token string
        """
        now = datetime.utcnow()
        exp = now + timedelta(days=expiry_days)

        payload = {
            'user_id': user_id,
            'exp': exp,
            'iat': now,
            'type': 'refresh'
        }

        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

        logger.info(f"Generated refresh token for user {user_id}")

        return token

    def verify_token(self, token: str) -> Dict[str, Any]:
        """
        Verify and decode JWT token.

        Args:
            token: JWT token string

        Returns:
            Decoded token payload

        Raises:
            AuthenticationError: If token is invalid or expired
        """
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm]
            )

            logger.debug(f"Verified token for user {payload.get('user_id')}")

            return payload

        except jwt.ExpiredSignatureError:
            logger.warning("Token expired")
            raise AuthenticationError("Token expired")

        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            raise AuthenticationError(f"Invalid token: {e}")

        except Exception as e:
            logger.error(f"Token verification failed: {e}")
            raise AuthenticationError(f"Token verification failed: {e}")

    def decode_token_without_verification(self, token: str) -> Dict[str, Any]:
        """
        Decode token without verification (for inspection only).

        Args:
            token: JWT token string

        Returns:
            Decoded payload (unverified)
        """
        try:
            payload = jwt.decode(
                token,
                options={"verify_signature": False}
            )
            return payload

        except Exception as e:
            logger.error(f"Failed to decode token: {e}")
            return {}

    def refresh_access_token(
        self,
        refresh_token: str,
        expiry_hours: int = 24
    ) -> str:
        """
        Generate new access token from refresh token.

        Args:
            refresh_token: Valid refresh token
            expiry_hours: New access token expiry

        Returns:
            New access token

        Raises:
            AuthenticationError: If refresh token is invalid
        """
        payload = self.verify_token(refresh_token)

        if payload.get('type') != 'refresh':
            raise AuthenticationError("Invalid refresh token")

        user_id = payload.get('user_id')
        if not user_id:
            raise AuthenticationError("Invalid refresh token payload")

        # Generate new access token (roles would be fetched from database)
        # For now, use empty roles list
        return self.generate_token(user_id, roles=[], expiry_hours=expiry_hours)

    def get_user_from_token(self, token: str) -> Optional[str]:
        """
        Extract user ID from token.

        Args:
            token: JWT token string

        Returns:
            User ID or None
        """
        try:
            payload = self.verify_token(token)
            return payload.get('user_id')
        except AuthenticationError:
            return None

    def get_roles_from_token(self, token: str) -> List[str]:
        """
        Extract roles from token.

        Args:
            token: JWT token string

        Returns:
            List of roles
        """
        try:
            payload = self.verify_token(token)
            return payload.get('roles', [])
        except AuthenticationError:
            return []

    def is_token_expired(self, token: str) -> bool:
        """
        Check if token is expired.

        Args:
            token: JWT token string

        Returns:
            True if expired
        """
        try:
            self.verify_token(token)
            return False
        except AuthenticationError as e:
            return "expired" in str(e).lower()

    def get_token_expiry(self, token: str) -> Optional[datetime]:
        """
        Get token expiration time.

        Args:
            token: JWT token string

        Returns:
            Expiration datetime or None
        """
        payload = self.decode_token_without_verification(token)
        exp_timestamp = payload.get('exp')

        if exp_timestamp:
            return datetime.fromtimestamp(exp_timestamp)

        return None

    def get_token_info(self, token: str) -> Dict[str, Any]:
        """
        Get information about token.

        Args:
            token: JWT token string

        Returns:
            Token information
        """
        payload = self.decode_token_without_verification(token)

        exp = payload.get('exp')
        iat = payload.get('iat')

        info = {
            'user_id': payload.get('user_id'),
            'roles': payload.get('roles', []),
            'type': payload.get('type', 'unknown'),
            'issued_at': datetime.fromtimestamp(iat).isoformat() if iat else None,
            'expires_at': datetime.fromtimestamp(exp).isoformat() if exp else None,
            'is_expired': self.is_token_expired(token)
        }

        return info
