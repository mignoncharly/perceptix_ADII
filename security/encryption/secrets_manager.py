"""
Secrets Manager

Encrypt secrets at rest using Fernet (symmetric encryption).
"""

import logging
import os
from pathlib import Path
from typing import Optional, Dict, Any
from cryptography.fernet import Fernet
import json


logger = logging.getLogger("SecretsManager")


class SecretsManager:
    """
    Encrypt secrets at rest using Fernet (symmetric encryption).

    Features:
    - AES-128-CBC encryption
    - Key rotation support
    - Environment variable integration
    - File-based secret storage
    """

    def __init__(self, key_path: str = ".secrets.key"):
        """
        Initialize secrets manager.

        Args:
            key_path: Path to encryption key file
        """
        self.key_path = Path(key_path)
        self.key = self._load_or_generate_key()
        self.cipher = Fernet(self.key)

        logger.info(f"Secrets manager initialized with key at {key_path}")

    def _load_or_generate_key(self) -> bytes:
        """Load existing key or generate new one."""
        if self.key_path.exists():
            with open(self.key_path, 'rb') as f:
                key = f.read()
            logger.info("Loaded existing encryption key")
            return key
        else:
            key = Fernet.generate_key()
            self._save_key(key)
            logger.info("Generated new encryption key")
            return key

    def _save_key(self, key: bytes):
        """Save encryption key to file."""
        # Ensure directory exists
        self.key_path.parent.mkdir(parents=True, exist_ok=True)

        with open(self.key_path, 'wb') as f:
            f.write(key)

        # Set restrictive permissions (Unix-like systems)
        try:
            os.chmod(self.key_path, 0o600)
        except Exception:
            pass  # Windows doesn't support chmod

        logger.info(f"Saved encryption key to {self.key_path}")

    def encrypt(self, secret: str) -> str:
        """
        Encrypt a secret string.

        Args:
            secret: Plain text secret

        Returns:
            Encrypted secret (base64 encoded)
        """
        if not secret:
            return ""

        encrypted = self.cipher.encrypt(secret.encode())
        return encrypted.decode('utf-8')

    def decrypt(self, encrypted: str) -> str:
        """
        Decrypt an encrypted secret.

        Args:
            encrypted: Encrypted secret (base64 encoded)

        Returns:
            Plain text secret
        """
        if not encrypted:
            return ""

        decrypted = self.cipher.decrypt(encrypted.encode())
        return decrypted.decode('utf-8')

    def encrypt_dict(self, secrets: Dict[str, str]) -> Dict[str, str]:
        """
        Encrypt all values in a dictionary.

        Args:
            secrets: Dictionary of secrets

        Returns:
            Dictionary with encrypted values
        """
        return {key: self.encrypt(value) for key, value in secrets.items()}

    def decrypt_dict(self, encrypted_secrets: Dict[str, str]) -> Dict[str, str]:
        """
        Decrypt all values in a dictionary.

        Args:
            encrypted_secrets: Dictionary of encrypted secrets

        Returns:
            Dictionary with decrypted values
        """
        return {key: self.decrypt(value) for key, value in encrypted_secrets.items()}

    def save_secrets_file(
        self,
        secrets: Dict[str, str],
        file_path: str,
        encrypt: bool = True
    ):
        """
        Save secrets to encrypted file.

        Args:
            secrets: Dictionary of secrets
            file_path: Path to save secrets
            encrypt: Whether to encrypt values
        """
        if encrypt:
            secrets_to_save = self.encrypt_dict(secrets)
        else:
            secrets_to_save = secrets

        with open(file_path, 'w') as f:
            json.dump(secrets_to_save, f, indent=2)

        logger.info(f"Saved {len(secrets)} secrets to {file_path}")

    def load_secrets_file(
        self,
        file_path: str,
        decrypt: bool = True
    ) -> Dict[str, str]:
        """
        Load secrets from encrypted file.

        Args:
            file_path: Path to secrets file
            decrypt: Whether to decrypt values

        Returns:
            Dictionary of secrets
        """
        with open(file_path, 'r') as f:
            secrets = json.load(f)

        if decrypt:
            return self.decrypt_dict(secrets)
        else:
            return secrets

    def rotate_key(self, new_key_path: Optional[str] = None):
        """
        Rotate encryption key.

        This requires re-encrypting all secrets with the new key.

        Args:
            new_key_path: Optional path for new key
        """
        # Generate new key
        new_key = Fernet.generate_key()
        new_cipher = Fernet(new_key)

        # Save new key
        if new_key_path:
            new_path = Path(new_key_path)
        else:
            new_path = self.key_path.with_suffix('.key.new')

        with open(new_path, 'wb') as f:
            f.write(new_key)

        try:
            os.chmod(new_path, 0o600)
        except Exception:
            pass

        logger.info(f"Generated new encryption key at {new_path}")
        logger.warning(
            "Key rotation requires re-encrypting all secrets. "
            "Use re_encrypt_secrets() method with old and new managers."
        )

        return new_path

    def get_key_info(self) -> Dict[str, Any]:
        """
        Get information about the encryption key.

        Returns:
            Key information
        """
        import stat

        key_stat = os.stat(self.key_path)

        return {
            'key_path': str(self.key_path),
            'key_exists': self.key_path.exists(),
            'key_size_bytes': key_stat.st_size,
            'key_created': key_stat.st_ctime,
            'key_modified': key_stat.st_mtime,
            'permissions': oct(stat.S_IMODE(key_stat.st_mode))
        }

    @staticmethod
    def re_encrypt_secrets(
        old_manager: 'SecretsManager',
        new_manager: 'SecretsManager',
        encrypted_data: Dict[str, str]
    ) -> Dict[str, str]:
        """
        Re-encrypt secrets with new key.

        Args:
            old_manager: Manager with old key
            new_manager: Manager with new key
            encrypted_data: Data encrypted with old key

        Returns:
            Data encrypted with new key
        """
        # Decrypt with old key
        decrypted = old_manager.decrypt_dict(encrypted_data)

        # Encrypt with new key
        re_encrypted = new_manager.encrypt_dict(decrypted)

        return re_encrypted

    def encrypt_env_vars(self, env_vars: Dict[str, str]) -> str:
        """
        Encrypt environment variables into a single encrypted string.

        Args:
            env_vars: Dictionary of environment variables

        Returns:
            Encrypted JSON string
        """
        json_str = json.dumps(env_vars)
        return self.encrypt(json_str)

    def decrypt_env_vars(self, encrypted_str: str) -> Dict[str, str]:
        """
        Decrypt environment variables from encrypted string.

        Args:
            encrypted_str: Encrypted JSON string

        Returns:
            Dictionary of environment variables
        """
        json_str = self.decrypt(encrypted_str)
        return json.loads(json_str)
