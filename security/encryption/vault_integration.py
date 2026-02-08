"""
HashiCorp Vault Integration

Optional integration with HashiCorp Vault for enterprise secrets management.
"""

import logging
from typing import Dict, Any, Optional, List


logger = logging.getLogger("VaultIntegration")


class VaultSecretsManager:
    """
    Integration with HashiCorp Vault for enterprise secrets management.

    Note: This requires hvac library and Vault server.
    Falls back gracefully if not available.
    """

    def __init__(
        self,
        vault_url: str,
        token: Optional[str] = None,
        mount_point: str = "secret"
    ):
        """
        Initialize Vault client.

        Args:
            vault_url: Vault server URL
            token: Vault authentication token
            mount_point: KV secrets engine mount point
        """
        self.vault_url = vault_url
        self.mount_point = mount_point
        self.client = None

        try:
            import hvac
            self.client = hvac.Client(url=vault_url, token=token)

            if self.client.is_authenticated():
                logger.info(f"Connected to Vault at {vault_url}")
            else:
                logger.warning("Vault authentication failed")
                self.client = None

        except ImportError:
            logger.warning(
                "hvac library not available. Install with: pip install hvac"
            )
            self.client = None
        except Exception as e:
            logger.error(f"Failed to connect to Vault: {e}")
            self.client = None

    def is_available(self) -> bool:
        """Check if Vault is available."""
        return self.client is not None and self.client.is_authenticated()

    def get_secret(self, path: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve secret from Vault.

        Args:
            path: Secret path (e.g., "cognizant/database")

        Returns:
            Secret data or None if not available
        """
        if not self.is_available():
            logger.warning("Vault not available")
            return None

        try:
            response = self.client.secrets.kv.v2.read_secret_version(
                path=path,
                mount_point=self.mount_point
            )

            return response['data']['data']

        except Exception as e:
            logger.error(f"Failed to get secret from Vault: {e}")
            return None

    def set_secret(self, path: str, secret: Dict[str, Any]) -> bool:
        """
        Store secret in Vault.

        Args:
            path: Secret path
            secret: Secret data

        Returns:
            True if successful
        """
        if not self.is_available():
            logger.warning("Vault not available")
            return False

        try:
            self.client.secrets.kv.v2.create_or_update_secret(
                path=path,
                secret=secret,
                mount_point=self.mount_point
            )

            logger.info(f"Stored secret at {path}")
            return True

        except Exception as e:
            logger.error(f"Failed to store secret in Vault: {e}")
            return False

    def delete_secret(self, path: str) -> bool:
        """
        Delete secret from Vault.

        Args:
            path: Secret path

        Returns:
            True if successful
        """
        if not self.is_available():
            logger.warning("Vault not available")
            return False

        try:
            self.client.secrets.kv.v2.delete_metadata_and_all_versions(
                path=path,
                mount_point=self.mount_point
            )

            logger.info(f"Deleted secret at {path}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete secret from Vault: {e}")
            return False

    def list_secrets(self, path: str = "") -> Optional[List[str]]:
        """
        List secrets at path.

        Args:
            path: Path to list

        Returns:
            List of secret names or None
        """
        if not self.is_available():
            logger.warning("Vault not available")
            return None

        try:
            response = self.client.secrets.kv.v2.list_secrets(
                path=path,
                mount_point=self.mount_point
            )

            return response['data']['keys']

        except Exception as e:
            logger.error(f"Failed to list secrets: {e}")
            return None

    def get_database_credentials(
        self,
        role: str,
        mount_point: str = "database"
    ) -> Optional[Dict[str, str]]:
        """
        Get dynamic database credentials from Vault.

        Args:
            role: Database role name
            mount_point: Database secrets engine mount point

        Returns:
            Credentials dictionary with 'username' and 'password'
        """
        if not self.is_available():
            logger.warning("Vault not available")
            return None

        try:
            response = self.client.secrets.database.generate_credentials(
                name=role,
                mount_point=mount_point
            )

            return {
                'username': response['data']['username'],
                'password': response['data']['password'],
                'lease_duration': response['lease_duration']
            }

        except Exception as e:
            logger.error(f"Failed to get database credentials: {e}")
            return None


class HybridSecretsManager:
    """
    Hybrid secrets manager that uses Vault when available,
    falls back to local SecretsManager.
    """

    def __init__(
        self,
        vault_url: Optional[str] = None,
        vault_token: Optional[str] = None,
        fallback_key_path: str = ".secrets.key"
    ):
        """
        Initialize hybrid secrets manager.

        Args:
            vault_url: Optional Vault URL
            vault_token: Optional Vault token
            fallback_key_path: Path for local encryption key
        """
        from security.encryption.secrets_manager import SecretsManager

        self.vault = None
        if vault_url and vault_token:
            self.vault = VaultSecretsManager(vault_url, vault_token)

        self.local_manager = SecretsManager(fallback_key_path)

        if self.vault and self.vault.is_available():
            logger.info("Using Vault for secrets management")
        else:
            logger.info("Using local secrets manager (Vault not available)")

    def get_secret(self, key: str) -> Optional[str]:
        """
        Get secret, trying Vault first, then local.

        Args:
            key: Secret key

        Returns:
            Secret value or None
        """
        # Try Vault first
        if self.vault and self.vault.is_available():
            vault_secret = self.vault.get_secret(f"cognizant/{key}")
            if vault_secret:
                return vault_secret.get('value')

        # Fall back to local (this would need a key-value store)
        # For now, return None
        logger.warning(f"Secret '{key}' not found in Vault or local storage")
        return None

    def is_vault_available(self) -> bool:
        """Check if Vault is available."""
        return self.vault is not None and self.vault.is_available()
