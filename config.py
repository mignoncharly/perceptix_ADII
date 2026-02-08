"""
Configuration Management System for Perceptix
Handles environment-based configuration, API key validation, and system modes.
"""
import os
import json
from typing import Optional, Dict, Any, List
from pathlib import Path
from dataclasses import dataclass, field
from dotenv import load_dotenv

# Load .env file
load_dotenv()

from models import SystemMode, Criticality
from exceptions import (
    ConfigurationError,
    InvalidAPIKeyError,
    InvalidModeError
)

DEFAULT_GEMINI_MODEL = "models/gemini-3-pro-preview"


@dataclass
class DatabaseConfig:
    """Database configuration settings."""
    type: str = "sqlite"  # sqlite, postgresql
    path: str = "perceptix_memory.db"
    host: str = "localhost"
    port: int = 5432
    name: str = "perceptix_db"
    user: Optional[str] = None
    password: Optional[str] = None
    connection_timeout: int = 30
    max_connections: int = 5
    pool_pre_ping: bool = True


@dataclass
class APIConfig:
    """API configuration settings."""
    gemini_api_key: Optional[str] = None
    model_name: str = DEFAULT_GEMINI_MODEL
    demo_username: str = "demo"
    demo_password: str = "secret"
    admin_users: List[str] = field(default_factory=lambda: ["demo"])
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: List[str] = field(default_factory=lambda: ["*"])
    max_retries: int = 3
    timeout_seconds: int = 60
    max_tokens: int = 8192
    temperature: float = 0.2
    
    # Security
    jwt_secret_key: Optional[str] = None
    jwt_algorithm: str = "HS256"
    jwt_expiration_hours: int = 24
    
    # Rate Limiting
    rate_limit_enabled: bool = False
    rate_limit_requests: int = 100
    rate_limit_window: int = 60


@dataclass
class ObserverConfig:
    """Observer configuration settings."""
    enable_simulation: bool = False
    telemetry_enabled: bool = True
    data_source_type: str = "sqlite"  # sqlite, snowflake, bigquery, postgres
    data_source_path: str = "data/source.db"
    confidence_threshold: float = 85.0
    monitored_tables: List[str] = field(default_factory=lambda: ["orders", "users", "products", "inventory"])
    table_timestamp_columns: Dict[str, str] = field(default_factory=dict)
    table_null_columns: Dict[str, List[str]] = field(default_factory=dict)
    warehouse_config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SystemConfig:
    """System-wide configuration settings."""
    mode: SystemMode = SystemMode.DEMO
    environment: str = "development"
    confidence_threshold: float = 85.0
    max_cycles: int = 1000
    enable_meta_learning: bool = True
    log_level: str = "INFO"
    version: str = "1.0.0"
    metrics_format: str = "prometheus"
    health_check_enabled: bool = True


@dataclass
class NotificationConfig:
    """Notification and alerting configuration."""
    enabled: bool = True
    channels: list = field(default_factory=lambda: ["console"])
    slack_webhook_url: Optional[str] = None
    email_smtp_host: Optional[str] = None
    email_smtp_port: int = 587
    email_from: Optional[str] = None
    email_to: Optional[str] = None
    email_password: Optional[str] = None
    email_use_tls: bool = True


@dataclass
class MLConfig:
    """Machine Learning configuration settings."""
    enabled: bool = False
    models_dir: str = "models_saved"
    enable_isolation_forest: bool = True
    enable_autoencoder: bool = True
    enable_forecaster: bool = False
    ensemble_threshold: float = 0.5
    auto_train: bool = False
    training_data_path: Optional[str] = None


@dataclass
class RemediationConfig:
    """Automated remediation configuration settings."""
    enabled: bool = False
    playbooks_dir: str = "remediation/playbooks"
    require_approval_for_production: bool = True
    approval_timeout_minutes: int = 30
    auto_execute_low_risk: bool = False
    dry_run_by_default: bool = True
    enable_slack_notifications: bool = False
    slack_webhook_url: Optional[str] = None


@dataclass
class TenancyConfig:
    """Multi-tenancy configuration settings."""
    enabled: bool = False
    tenant_db_path: str = "perceptix_tenants.db"
    require_tenant_header: bool = False
    default_tenant: Optional[str] = "demo"
    isolation_strategy: str = "shared_schema"  # shared_schema, separate_schema, separate_database
    enable_tenant_resolver: bool = True
    allow_subdomain_resolution: bool = False
    allow_api_key_resolution: bool = True


@dataclass
class RulesEngineConfig:
    """Custom alerting rules engine configuration settings."""
    enabled: bool = True
    rules_path: str = "rules"
    cooldown_db_path: str = "rules_cooldown.db"
    auto_reload_rules: bool = False
    reload_interval_minutes: int = 5
    enable_rule_validation: bool = True
    max_rules: int = 100
    enable_cooldown: bool = True
    enable_rate_limiting: bool = True


@dataclass
class SlackBotConfig:
    """Slack bot configuration settings."""
    enabled: bool = False
    bot_token: Optional[str] = None
    app_token: Optional[str] = None
    signing_secret: Optional[str] = None
    default_channel: str = "#data-ops"
    enable_threading: bool = True
    enable_buttons: bool = True
    enable_daily_summary: bool = False
    daily_summary_hour: int = 9
    daily_summary_minute: int = 0
    enable_weekly_report: bool = False
    weekly_report_day: int = 1  # Monday
    weekly_report_hour: int = 9
    mock_mode: bool = True  # For testing without real Slack


@dataclass
class PerceptixConfig:
    """Complete configuration for Perceptix system."""
    system: SystemConfig = field(default_factory=SystemConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    api: APIConfig = field(default_factory=APIConfig)
    observer: ObserverConfig = field(default_factory=ObserverConfig)
    notification: NotificationConfig = field(default_factory=NotificationConfig)
    ml: MLConfig = field(default_factory=MLConfig)
    remediation: RemediationConfig = field(default_factory=RemediationConfig)
    tenancy: TenancyConfig = field(default_factory=TenancyConfig)
    rules_engine: RulesEngineConfig = field(default_factory=RulesEngineConfig)
    slack_bot: SlackBotConfig = field(default_factory=SlackBotConfig)

    def validate(self) -> None:
        """
        Validate configuration settings.

        Raises:
            ConfigurationError: If configuration is invalid
            InvalidAPIKeyError: If API key is required but missing/invalid
            InvalidModeError: If system mode is invalid
        """
        # Validate system mode
        if self.system.mode not in [SystemMode.PRODUCTION, SystemMode.DEMO, SystemMode.MOCK]:
            raise InvalidModeError(
                f"Invalid system mode: {self.system.mode}",
                component="ConfigManager"
            )

        # In PRODUCTION mode, API key is mandatory
        if self.system.mode == SystemMode.PRODUCTION:
            if not self.api.gemini_api_key:
                raise InvalidAPIKeyError(
                    "API key is required in PRODUCTION mode",
                    component="ConfigManager",
                    context={"mode": self.system.mode.value}
                )

            if not self._validate_api_key_format(self.api.gemini_api_key):
                raise InvalidAPIKeyError(
                    "API key format is invalid",
                    component="ConfigManager"
                )

        # Validate confidence threshold
        if not 0.0 <= self.system.confidence_threshold <= 100.0:
            raise ConfigurationError(
                f"Confidence threshold must be between 0 and 100, got {self.system.confidence_threshold}",
                component="ConfigManager"
            )

        # Validate database path
        if self.system.mode == SystemMode.PRODUCTION:
            db_path = Path(self.database.path)
            db_dir = db_path.parent
            if not db_dir.exists():
                raise ConfigurationError(
                    f"Database directory does not exist: {db_dir}",
                    component="ConfigManager"
                )

        # Validate temperature
        if not 0.0 <= self.api.temperature <= 2.0:
            raise ConfigurationError(
                f"API temperature must be between 0.0 and 2.0, got {self.api.temperature}",
                component="ConfigManager"
            )

    @staticmethod
    def _validate_api_key_format(api_key: str) -> bool:
        """
        Validate API key format (basic check).

        Args:
            api_key: The API key to validate

        Returns:
            bool: True if format is valid
        """
        if not api_key or not isinstance(api_key, str):
            return False

        # Google API keys typically start with AIza and are ~39 chars
        # This is a basic format check
        if len(api_key) < 20:
            return False

        return True

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary (excluding sensitive data)."""
        return {
            "system": {
                "mode": self.system.mode.value,
                "environment": self.system.environment,
                "confidence_threshold": self.system.confidence_threshold,
                "version": self.system.version
            },
            "database": {
                "path": self.database.path,
                "max_connections": self.database.max_connections
            },
            "api": {
                "model_name": self.api.model_name,
                "has_api_key": bool(self.api.gemini_api_key),
                "max_retries": self.api.max_retries,
                "timeout_seconds": self.api.timeout_seconds
            },
            "observer": {
                "enable_simulation": self.observer.enable_simulation,
                "telemetry_enabled": self.observer.telemetry_enabled,
                "data_source_type": self.observer.data_source_type
            }
        }


class ConfigManager:
    """
    Manages configuration loading from environment variables and files.
    Implements fail-fast principle for invalid configurations.
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize configuration manager.

        Args:
            config_path: Optional path to JSON config file

        Raises:
            ConfigurationError: If configuration cannot be loaded
        """
        self.config_path = config_path
        self._config: Optional[PerceptixConfig] = None

    def load(self) -> PerceptixConfig:
        """
        Load configuration from environment and optional file.
        Priority: Environment Variables > Config File > Defaults

        Returns:
            PerceptixConfig: Validated configuration

        Raises:
            ConfigurationError: If configuration is invalid
        """
        config = PerceptixConfig()

        # Load from file if provided
        if self.config_path:
            config = self._load_from_file(self.config_path)

        # Override with environment variables
        config = self._load_from_environment(config)

        # Validate configuration
        config.validate()

        self._config = config
        return config

    def _load_from_file(self, file_path: str) -> PerceptixConfig:
        """
        Load configuration from JSON file.

        Args:
            file_path: Path to configuration file

        Returns:
            PerceptixConfig: Configuration object

        Raises:
            ConfigurationError: If file cannot be loaded
        """
        try:
            path = Path(file_path)
            if not path.exists():
                raise ConfigurationError(
                    f"Configuration file not found: {file_path}",
                    component="ConfigManager"
                )

            with open(path, 'r') as f:
                data = json.load(f)

            # Reconstruct config from JSON
            config = PerceptixConfig()

            # System config
            if 'system' in data:
                sys_data = data['system']
                config.system.mode = SystemMode(sys_data.get('mode', 'DEMO'))
                config.system.environment = sys_data.get('environment', 'development')
                config.system.confidence_threshold = sys_data.get('confidence_threshold', 85.0)
                config.system.max_cycles = sys_data.get('max_cycles', 1000)
                config.system.log_level = sys_data.get('log_level', 'INFO')

            # Database config
            if 'database' in data:
                db_data = data['database']
                config.database.path = db_data.get('path', 'perceptix_memory.db')
                config.database.max_connections = db_data.get('max_connections', 5)

            # API config
            if 'api' in data:
                api_data = data['api']
                config.api.model_name = api_data.get('model_name', DEFAULT_GEMINI_MODEL)
                config.api.max_retries = api_data.get('max_retries', 3)
                config.api.timeout_seconds = api_data.get('timeout_seconds', 60)
                config.api.temperature = api_data.get('temperature', 0.2)

            return config

        except json.JSONDecodeError as e:
            raise ConfigurationError(
                f"Invalid JSON in configuration file: {e}",
                component="ConfigManager"
            )
        except Exception as e:
            raise ConfigurationError(
                f"Error loading configuration file: {e}",
                component="ConfigManager"
            )

    def _load_from_environment(self, config: PerceptixConfig) -> PerceptixConfig:
        """
        Override configuration with environment variables.

        Args:
            config: Base configuration to override

        Returns:
            PerceptixConfig: Configuration with environment overrides
        """
        # System mode
        mode_str = os.getenv('PERCEPTIX_MODE', '').upper()
        if mode_str:
            try:
                config.system.mode = SystemMode(mode_str)
            except ValueError:
                raise InvalidModeError(
                    f"Invalid PERCEPTIX_MODE: {mode_str}",
                    component="ConfigManager"
                )

        # Environment
        config.system.environment = os.getenv('PERCEPTIX_ENVIRONMENT', config.system.environment)

        # API Key (most important)
        api_key = os.getenv('GEMINI_API_KEY')
        if api_key:
            config.api.gemini_api_key = api_key

        # Model name
        model_name = os.getenv('GEMINI_MODEL_NAME')
        if model_name:
            config.api.model_name = model_name

        demo_username = os.getenv('DEMO_USERNAME')
        if demo_username:
            config.api.demo_username = demo_username

        demo_password = os.getenv('DEMO_PASSWORD')
        if demo_password:
            config.api.demo_password = demo_password

        admin_users = os.getenv('ADMIN_USERS')
        if admin_users:
            config.api.admin_users = [user.strip() for user in admin_users.split(',') if user.strip()]
        else:
            admin_username = os.getenv('ADMIN_USERNAME')
            if admin_username:
                config.api.admin_users = [admin_username]

        # Confidence threshold
        threshold = os.getenv('PERCEPTIX_CONFIDENCE_THRESHOLD')
        if threshold:
            try:
                config.system.confidence_threshold = float(threshold)
            except ValueError:
                raise ConfigurationError(
                    f"Invalid confidence threshold: {threshold}",
                    component="ConfigManager"
                )

        # Support alias CONFIDENCE_THRESHOLD
        threshold_alias = os.getenv('CONFIDENCE_THRESHOLD')
        if threshold_alias:
            try:
                config.system.confidence_threshold = float(threshold_alias)
            except ValueError:
                pass

        # Database path
        db_path = os.getenv('PERCEPTIX_DB_PATH')
        if db_path:
            config.database.path = db_path

        # Log level
        log_level = os.getenv('PERCEPTIX_LOG_LEVEL')
        if log_level:
            config.system.log_level = log_level.upper()

        # Notification settings
        slack_webhook = os.getenv('SLACK_WEBHOOK_URL')
        if slack_webhook:
            config.notification.slack_webhook_url = slack_webhook
            if 'slack' not in config.notification.channels:
                config.notification.channels.append('slack')

        # Email settings
        email_smtp_host = os.getenv('EMAIL_SMTP_HOST')
        if email_smtp_host:
            config.notification.email_smtp_host = email_smtp_host

        email_smtp_port = os.getenv('EMAIL_SMTP_PORT')
        if email_smtp_port:
            config.notification.email_smtp_port = int(email_smtp_port)

        email_from = os.getenv('EMAIL_FROM')
        if email_from:
            config.notification.email_from = email_from

        email_to = os.getenv('EMAIL_TO')
        if email_to:
            config.notification.email_to = email_to

        email_password = (
            os.getenv('EMAIL_PASSWORD')
            or os.getenv('EMAIL_APP_PASSWORD')
            or os.getenv('SMTP_PASSWORD')
        )
        if email_password:
            config.notification.email_password = email_password

        email_use_tls = os.getenv('EMAIL_USE_TLS') or os.getenv('EMAIL_SMTP_USE_TLS')
        if email_use_tls:
            config.notification.email_use_tls = email_use_tls.lower() in ('true', '1', 'yes')

        # Enable email channel automatically when core SMTP settings are present
        if (
            config.notification.email_smtp_host
            and config.notification.email_from
            and config.notification.email_to
            and 'email' not in config.notification.channels
        ):
            config.notification.channels.append('email')

        # Observer monitored tables and per-table config (optional).
        monitored_tables = os.getenv("PERCEPTIX_MONITORED_TABLES")
        if monitored_tables:
            config.observer.monitored_tables = [t.strip() for t in monitored_tables.split(",") if t.strip()]

        ts_map = os.getenv("PERCEPTIX_TABLE_TIMESTAMP_COLUMNS")
        if ts_map:
            try:
                config.observer.table_timestamp_columns = json.loads(ts_map)
            except Exception:
                pass

        null_cols_map = os.getenv("PERCEPTIX_TABLE_NULL_COLUMNS")
        if null_cols_map:
            try:
                config.observer.table_null_columns = json.loads(null_cols_map)
            except Exception:
                pass

        # Tenancy settings
        tenancy_enabled = os.getenv("TENANCY_ENABLED") or os.getenv("PERCEPTIX_TENANCY_ENABLED")
        if tenancy_enabled:
            config.tenancy.enabled = tenancy_enabled.lower() in ("1", "true", "yes", "on")

        tenant_db_path = os.getenv("TENANT_DB_PATH") or os.getenv("PERCEPTIX_TENANT_DB_PATH")
        if tenant_db_path:
            config.tenancy.tenant_db_path = tenant_db_path

        default_tenant = os.getenv("DEFAULT_TENANT") or os.getenv("PERCEPTIX_DEFAULT_TENANT")
        if default_tenant:
            config.tenancy.default_tenant = default_tenant

        require_tenant = os.getenv("REQUIRE_TENANT_HEADER") or os.getenv("PERCEPTIX_REQUIRE_TENANT_HEADER")
        if require_tenant:
            config.tenancy.require_tenant_header = require_tenant.lower() in ("1", "true", "yes", "on")

        # Database settings
        db_type = os.getenv('DB_TYPE')
        if db_type:
            config.database.type = db_type
        
        db_name = os.getenv('DB_NAME')
        if db_name:
            config.database.name = db_name
        
        db_user = os.getenv('DB_USER')
        if db_user:
            config.database.user = db_user
            
        db_pass = os.getenv('DB_PASSWORD')
        if db_pass:
            config.database.password = db_pass
            
        db_host = os.getenv('DB_HOST')
        if db_host:
            config.database.host = db_host
            
        db_port = os.getenv('DB_PORT')
        if db_port:
            config.database.port = int(db_port)

        # API & Server
        api_host = os.getenv('API_HOST')
        if api_host:
            config.api.host = api_host
            
        api_port = os.getenv('API_PORT')
        if api_port:
            config.api.port = int(api_port)
            
        cors = os.getenv('CORS_ORIGINS')
        if cors:
            config.api.cors_origins = [o.strip() for o in cors.split(',')]

        # Security
        jwt_secret = os.getenv('JWT_SECRET_KEY')
        if jwt_secret:
            config.api.jwt_secret_key = jwt_secret
            
        jwt_algo = os.getenv('JWT_ALGORITHM')
        if jwt_algo:
            config.api.jwt_algorithm = jwt_algo
            
        jwt_exp = os.getenv('JWT_EXPIRATION_HOURS')
        if jwt_exp:
            config.api.jwt_expiration_hours = int(jwt_exp)

        # Rate Limiting
        rl_enabled = os.getenv('RATE_LIMIT_ENABLED')
        if rl_enabled:
            config.api.rate_limit_enabled = rl_enabled.lower() in ('true', '1', 'yes')
            
        rl_req = os.getenv('RATE_LIMIT_REQUESTS')
        if rl_req:
            config.api.rate_limit_requests = int(rl_req)
            
        rl_win = os.getenv('RATE_LIMIT_WINDOW')
        if rl_win:
            config.api.rate_limit_window = int(rl_win)

        # ML settings
        ml_enabled = os.getenv('ML_ENABLED')
        if ml_enabled:
            config.ml.enabled = ml_enabled.lower() in ('true', '1', 'yes')

        ml_models_dir = os.getenv('ML_MODELS_DIR')
        if ml_models_dir:
            config.ml.models_dir = ml_models_dir

        # Rules Engine settings
        rules_enabled = os.getenv('RULES_ENABLED')
        if rules_enabled:
            config.rules_engine.enabled = rules_enabled.lower() in ('true', '1', 'yes')
            
        rules_path = os.getenv('RULES_PATH')
        if rules_path:
            config.rules_engine.rules_path = rules_path
            
        cooldown_path = os.getenv('COOLDOWN_DB_PATH')
        if cooldown_path:
            config.rules_engine.cooldown_db_path = cooldown_path

        # Tenancy settings
        tenancy_enabled = os.getenv('TENANCY_ENABLED')
        if tenancy_enabled:
            config.tenancy.enabled = tenancy_enabled.lower() in ('true', '1', 'yes')
            
        tenant_db = os.getenv('TENANT_DB_PATH')
        if tenant_db:
            config.tenancy.tenant_db_path = tenant_db

        # Slack Bot settings
        slack_enabled = os.getenv('SLACK_BOT_ENABLED')
        if slack_enabled:
            config.slack_bot.enabled = slack_enabled.lower() in ('true', '1', 'yes')
            
        slack_bot_token = os.getenv('SLACK_BOT_TOKEN')
        if slack_bot_token:
            config.slack_bot.bot_token = slack_bot_token
            
        slack_app_token = os.getenv('SLACK_APP_TOKEN')
        if slack_app_token:
            config.slack_bot.app_token = slack_app_token
            
        slack_sig = os.getenv('SLACK_SIGNING_SECRET')
        if slack_sig:
            config.slack_bot.signing_secret = slack_sig

        # Observability
        metrics_fmt = os.getenv('METRICS_FORMAT')
        if metrics_fmt:
            config.system.metrics_format = metrics_fmt
            
        health_check = os.getenv('HEALTH_CHECK_ENABLED')
        if health_check:
            config.system.health_check_enabled = health_check.lower() in ('true', '1', 'yes')

        # DataSource settings
        ds_type = os.getenv('DATA_SOURCE_TYPE')
        if ds_type:
            config.observer.data_source_type = ds_type

        return config

    @property
    def config(self) -> PerceptixConfig:
        """
        Get current configuration.

        Returns:
            PerceptixConfig: Current configuration

        Raises:
            ConfigurationError: If configuration not loaded
        """
        if self._config is None:
            raise ConfigurationError(
                "Configuration not loaded. Call load() first.",
                component="ConfigManager"
            )
        return self._config


# Singleton instance
_config_manager: Optional[ConfigManager] = None


def get_config_manager(config_path: Optional[str] = None) -> ConfigManager:
    """
    Get singleton ConfigManager instance.

    Args:
        config_path: Optional path to configuration file

    Returns:
        ConfigManager: Singleton instance
    """
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager(config_path)
    return _config_manager


def load_config(config_path: Optional[str] = None) -> PerceptixConfig:
    """
    Load and validate configuration.

    Args:
        config_path: Optional path to configuration file

    Returns:
        PerceptixConfig: Validated configuration

    Raises:
        ConfigurationError: If configuration is invalid
    """
    manager = get_config_manager(config_path)
    return manager.load()


def apply_dynamic_settings(config: PerceptixConfig, settings: Dict[str, str]) -> None:
    """
    Overlay dynamic settings from database onto the config object.
    
    Args:
        config: The configuration object to update
        settings: Dictionary of key-value settings from DB
    """
    # System
    if "system.confidence_threshold" in settings:
        try:
            val = float(settings["system.confidence_threshold"])
            if 0 <= val <= 100:
                config.system.confidence_threshold = val
        except ValueError:
            pass
            
    if "system.max_cycles" in settings:
        try:
            config.system.max_cycles = int(settings["system.max_cycles"])
        except ValueError:
            pass
            
    # API
    if "api.temperature" in settings:
        try:
            config.api.temperature = float(settings["api.temperature"])
        except ValueError:
            pass
            
    # ML
    if "ml.enabled" in settings:
        config.ml.enabled = settings["ml.enabled"].lower() in ('true', '1', 'yes')
        
    if "ml.ensemble_threshold" in settings:
        try:
            config.ml.ensemble_threshold = float(settings["ml.ensemble_threshold"])
        except ValueError:
            pass
            
    # Rules
    if "rules_engine.enabled" in settings:
         config.rules_engine.enabled = settings["rules_engine.enabled"].lower() in ('true', '1', 'yes')
         
    # Notifications
    if "notification.enabled" in settings:
        config.notification.enabled = settings["notification.enabled"].lower() in ('true', '1', 'yes')
