import hashlib
import hmac
import secrets
from datetime import datetime
from typing import Optional
from pydantic import BaseModel

from cryptography.fernet import Fernet
from fastapi import HTTPException, Security, status
from fastapi.security.api_key import APIKeyHeader
from loguru import logger

from src.core.config import settings


class APIKeyMetadata(BaseModel):
    """Metadata for API key tracking."""

    key_hash: str
    created_at: datetime
    last_used: datetime | None = None
    usage_count: int = 0
    is_active: bool = True
    rate_limit: int = 100  # requests per minute

class SecureAPIKeyManager:
    """
    Manages encrypted API keys with rotation support.
    
    Features:
    - Encrypt/decrypt API keys at runtime
    - Track key usage
    - Support key rotation
    - Rate limiting per key
    """
    def __init__(self):
        self.encryption_key = self._get_or_create_encryption_key()
        self.cipher_suite = Fernet(self.encryption_key)
        self._key_metadata: dict[str, APIKeyMetadata] = {}

    def _get_or_create_encryption_key(self) -> bytes:
        """
        Get or create an encryption key.

        Returns:
            bytes: The encryption key.
        """
        if hasattr(settings, "ENCRYPTION_KEY") and settings.ENCRYPTION_KEY:
            return settings.ENCRYPTION_KEY.encode()
        
        key = Fernet.generate_key()
        logger.warning(
            "⚠️  Generated new encryption key. "
            "Save this to ENCRYPTION_KEY environment variable!"
        )
        return key

    def encrypt_api_keys(self, api_key: list[str]) -> str:
        """
        Encrypt an API key.

        Args:
            api_key: The API key to encrypt.

        Returns:
            str: The encrypted API key.
        """
        key_string = "".join(api_key)
        encrypted_key = self.cipher_suite.encrypt(key_string.encode())
        return encrypted_key.decode()
    
    def decrypt_api_keys(self, encrypted_key: str) -> list[str]:
        """
        Decrypt an API key.

        Args:
            encrypted_key: The encrypted API key.

        Returns:
            list[str]: The decrypted API key.
        """
        try:
            decrypted = self.cipher_suite.decrypt(encrypted_key.encode())
            keys = decrypted.decode().split(",")
            return [key.strip() for key in keys if key.strip()]
        except Exception as e:
            logger.error(f"Failed to decrypt API key: {e}")
            raise ValueError("Invalid API key") from e
        
    def hash_api_key(self, api_key: str) -> str:
        """
        Hash an API key.

        Args:
            api_key: The API key to hash.

        Returns:
            str: The hashed API key.
        """
        return hashlib.sha256(api_key.encode()).hexdigest()

    def verify_api_key(self, api_key: str, valid_keys: list[str]) -> bool:
        """
        Verify an API key.

        Args:
            api_key: The API key to verify.
            valid_keys: List of valid API keys.

        Returns:
            bool: True if the API key is valid, False otherwise.
        """
        provided_hash = self.hash_api_key(api_key)
        for valid_key in valid_keys:
            valid_hash = self.hash_api_key(valid_key)
            if hmac.compare_digest(provided_hash, valid_hash):
                self._update_key_metadata(provided_hash)
                return True
            
        return False

    def _update_key_metadata(self, key_hash: str) -> None:
        """
        Update key metadata.

        Args:
            key_hash: The hash of the API key.
        """
        if key_hash not in self._key_metadata:
            self._key_metadata[key_hash] = APIKeyMetadata(
                key_hash=key_hash, created_at=datetime.now()
            )
        metadata = self._key_metadata[key_hash]
        metadata.last_used = datetime.now()
        metadata.usage_count += 1
    
    def get_key_metadata(self, api_key: str) -> Optional[APIKeyMetadata]:
        """
        Get key metadata.

        Args:
            api_key: The API key.

        Returns:
            Optional[APIKeyMetadata]: The key metadata or None if not found.
        """
        key_hash = self.hash_api_key(api_key)
        return self._key_metadata.get(key_hash)
    
    # def is_rate_limited(self, api_key: str, window_seconds: int = 60) -> bool:
    #     """
    #     Check if an API key is rate limited.

    #     Args:
    #         api_key: The API key.
    #         window_seconds: The time window in seconds.

    #     Returns:
    #         bool: True if the API key is rate limited, False otherwise.
    #     """
    #     metadata = self.get_key_metadata(api_key)
    #     if not metadata or not metadata.last_used:
    #         return False
        
    #     time_since_last_use = (datetime.now() - metadata.last_used).total_seconds()
    #     if time_since_last_use > window_seconds:
    #         return False

    #     # TODO
    #     # Simple rate limit check - in production use Redis
    #     requests_per_second = metadata.usage_count / max(time_since_last_use, 1)
    #     max_requests_per_second = metadata.rate_limit #/ 60

    #     return requests_per_second > max_requests_per_second

# Global instance
api_key_manager = SecureAPIKeyManager()
api_key_header = APIKeyHeader(name="X-API-KEY", auto_error=False)

async def validate_api_key(api_key: str = Security(api_key_header)) -> str:
    """
    Validate API key from header

    Args:
        api_key: API key from X-API-Key header

    Returns:
        str: Validated API key

    Raises:
        HTTPException: If API key is invalid or missing
    """
    if not api_key:
        logger.warning("Missing API key in request")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Include X-API-KEY header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    try:
        valid_keys = settings.api_keys_list
    except Exception as e:
        logger.error(f"Failed to load API keys: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service unavailable",
        ) from e
    
    if not api_key_manager.verify_api_key(api_key, valid_keys):
        logger.warning(f"Invalid API key: {api_key[:6]}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key, Access forbidden",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    
    # # check rate limit
    # if api_key_manager.is_rate_limited(api_key):
    #     logger.warning(f"Rate limited API key: {api_key[:6]}")
    #     raise HTTPException(
    #         status_code=status.HTTP_429_TOO_MANY_REQUESTS,
    #         detail="Rate limit exceeded",
    #         headers={"WWW-Authenticate": "ApiKey"},
    #     )
    
    return api_key
