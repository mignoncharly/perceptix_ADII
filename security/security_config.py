"""
Security Configuration

Security headers, rate limiting, and best practices.
"""

from dataclasses import dataclass, field
from typing import Dict, Optional
from enum import Enum


# Security headers for HTTP responses
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Content-Security-Policy": "default-src 'self'",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()"
}


# Rate limits for API endpoints (requests per time period)
RATE_LIMITS = {
    "api/v1/cycles/trigger": "10/minute",
    "api/v1/incidents": "100/minute",
    "api/v1/metrics": "60/minute",
    "api/v1/rules": "30/minute",
    "api/v1/config": "10/minute",
    "default": "120/minute"
}


# Password policy
PASSWORD_POLICY = {
    "min_length": 12,
    "require_uppercase": True,
    "require_lowercase": True,
    "require_numbers": True,
    "require_special": True,
    "expiry_days": 90,
    "history_count": 5,  # Don't reuse last N passwords
    "max_attempts": 5,   # Lock after N failed attempts
    "lockout_duration_minutes": 30
}


@dataclass
class SecurityConfig:
    """Security configuration."""

    # JWT settings
    jwt_secret: str = "CHANGE_ME_IN_PRODUCTION"
    jwt_algorithm: str = "HS256"
    jwt_expiry_hours: int = 24
    refresh_token_expiry_days: int = 30

    # Encryption settings
    secrets_key_path: str = ".secrets.key"
    vault_url: Optional[str] = None
    vault_token: Optional[str] = None
    use_vault: bool = False

    # Audit logging
    audit_log_path: str = "audit_log.db"
    audit_siem_enabled: bool = False
    audit_siem_endpoint: Optional[str] = None

    # Rate limiting
    rate_limiting_enabled: bool = True
    rate_limits: Dict[str, str] = field(default_factory=lambda: RATE_LIMITS.copy())

    # Security headers
    security_headers_enabled: bool = True
    security_headers: Dict[str, str] = field(default_factory=lambda: SECURITY_HEADERS.copy())

    # CORS settings
    cors_enabled: bool = True
    cors_origins: list = field(default_factory=lambda: ["http://localhost:3000"])
    cors_allow_credentials: bool = True

    # API keys
    api_keys: Dict[str, Dict] = field(default_factory=dict)

    # Session settings
    session_timeout_minutes: int = 60
    remember_me_days: int = 30

    # Account security
    max_login_attempts: int = 5
    lockout_duration_minutes: int = 30
    password_policy: Dict = field(default_factory=lambda: PASSWORD_POLICY.copy())

    # Multi-factor authentication
    mfa_enabled: bool = False
    mfa_required_for_roles: list = field(default_factory=lambda: ["admin"])

    # IP whitelisting/blacklisting
    ip_whitelist: list = field(default_factory=list)
    ip_blacklist: list = field(default_factory=list)

    # TLS/SSL
    require_https: bool = False
    hsts_max_age: int = 31536000

    def validate(self) -> list:
        """
        Validate security configuration.

        Returns:
            List of validation errors
        """
        errors = []

        # Check JWT secret
        if self.jwt_secret == "CHANGE_ME_IN_PRODUCTION":
            errors.append("JWT secret must be changed in production")

        if len(self.jwt_secret) < 32:
            errors.append("JWT secret should be at least 32 characters")

        # Check Vault configuration
        if self.use_vault and not self.vault_url:
            errors.append("Vault URL required when use_vault is True")

        # Check CORS origins
        if self.cors_enabled and "*" in self.cors_origins:
            errors.append("Using '*' for CORS origins is insecure")

        # Check password policy
        if self.password_policy['min_length'] < 8:
            errors.append("Minimum password length should be at least 8")

        return errors

    def get_security_warnings(self) -> list:
        """
        Get security warnings for current configuration.

        Returns:
            List of security warnings
        """
        warnings = []

        # Check production readiness
        if not self.require_https:
            warnings.append("HTTPS not required - insecure for production")

        if not self.rate_limiting_enabled:
            warnings.append("Rate limiting disabled - vulnerable to abuse")

        if not self.audit_siem_enabled:
            warnings.append("SIEM integration disabled - limited audit visibility")

        if not self.mfa_enabled:
            warnings.append("MFA disabled - accounts vulnerable to compromise")

        if self.jwt_expiry_hours > 24:
            warnings.append("JWT expiry > 24 hours - reduces security")

        if not self.security_headers_enabled:
            warnings.append("Security headers disabled")

        return warnings


# Predefined security profiles
class SecurityProfile(str, Enum):
    """Security profile presets."""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    HIGH_SECURITY = "high_security"


def get_security_config_for_profile(profile: SecurityProfile) -> SecurityConfig:
    """
    Get security configuration for a profile.

    Args:
        profile: Security profile

    Returns:
        SecurityConfig instance
    """
    if profile == SecurityProfile.DEVELOPMENT:
        return SecurityConfig(
            jwt_secret="dev-secret-key-not-for-production",
            require_https=False,
            rate_limiting_enabled=False,
            audit_siem_enabled=False,
            mfa_enabled=False
        )

    elif profile == SecurityProfile.STAGING:
        return SecurityConfig(
            jwt_secret="staging-secret-key-change-in-production",
            require_https=True,
            rate_limiting_enabled=True,
            audit_siem_enabled=False,
            mfa_enabled=False
        )

    elif profile == SecurityProfile.PRODUCTION:
        return SecurityConfig(
            jwt_secret="CHANGE_ME_IN_PRODUCTION",
            require_https=True,
            rate_limiting_enabled=True,
            audit_siem_enabled=True,
            mfa_enabled=False,
            cors_origins=[]  # Must be explicitly configured
        )

    elif profile == SecurityProfile.HIGH_SECURITY:
        return SecurityConfig(
            jwt_secret="CHANGE_ME_IN_PRODUCTION",
            jwt_expiry_hours=8,
            require_https=True,
            rate_limiting_enabled=True,
            audit_siem_enabled=True,
            mfa_enabled=True,
            use_vault=True,
            cors_origins=[],
            password_policy={
                **PASSWORD_POLICY,
                "min_length": 16,
                "max_attempts": 3,
                "lockout_duration_minutes": 60
            }
        )

    else:
        return SecurityConfig()
