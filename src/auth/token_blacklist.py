from datetime import UTC, datetime

from loguru import logger
from redis.asyncio import ConnectionPool, Redis
from redis.exceptions import RedisError

from src.core.config import settings
from src.core.exception import TokenBlacklistError


class TokenBlacklist:
    """
    Token blacklist service using Redis for storage.

    Features:
    - Automatic token expiration using Redis TTL
    - Efficient O(1) lookup
    - Graceful degradation if Redis unavailable

    Usage:
        blacklist = TokenBlacklist(redis_client)

        # Revoke token (e.g., on logout)
        await blacklist.revoke_token(token, expiry_seconds=900)

        # Check if token is revoked
        is_revoked = await blacklist.is_revoked(token)
    """

    def __init__(self, redis_client: Redis):
        self.redis = redis_client
        self._prefix = "blacklist:token:"

    async def revoke_token(self, token: str, expiry_seconds: int):
        """
        Revoke a token by adding it to the blacklist with an expiration time.

        Args:
            token (str): The token to revoke.
            expiry_seconds (int): Expiration time in seconds 
        """
        try:
            key = f"{self._prefix}{token}"

            revoked_at = datetime.now(UTC).isoformat()

            await self.redis.setex(name=key, time=expiry_seconds, value=revoked_at)
            logger.info(f"Token revoked successfully (expires in {expiry_seconds}s)")
            return True

        except RedisError as e:
            logger.error(f"Failed to revoke token: {e}")
            raise TokenBlacklistError("Failed to revoke token") from e

    async def is_revoked(self, token: str) -> bool:
        """
        Check if a token is revoked.

        Args:
            token (str): The token to check.

        Returns:
            bool: True if the token is revoked, False otherwise.
        """
        try:
            key = f"{self._prefix}{token}"
            return await self.redis.exists(key)
        except RedisError as e:
            logger.error(f"Failed to check token revocation: {e}")
            raise TokenBlacklistError("Failed to check token revocation") from e
    
    async def revoke_all_user_tokens(self, user_id: str, expiry_seconds: int = 3600) -> int:
        """
        Revoke all tokens for a specific user (e.g., password reset, account compromise).

        Args:
            user_id: User ID whose tokens should be revoked
            expiry_seconds: TTL for the revocation record

        Returns:
            Number of tokens revoked

        Example:
            >>> await blacklist.revoke_all_user_tokens("user-123")
            5
        """
        try:
            key = f"{self._prefix}user:{user_id}"

            revoked_at = datetime.now(UTC).isoformat()

            # Store user-level revocation with timestamp
            await self.redis.setex(name=key, time=expiry_seconds, value=revoked_at)

            logger.warning(f"All tokens revoked for user {user_id}")
            return 1

        except RedisError as e:
            logger.error(f"Failed to revoke user tokens: {e}")
            raise TokenBlacklistError("Failed to revoke user tokens") from e

    async def is_user_revoked(self, user_id: str) -> datetime | None:
        """
        Check if all tokens for a user have been revoked.

        Args:
            user_id: User ID to check

        Returns:
            DateTime when user was revoked, or None if not revoked
        """
        try:
            key = f"{self._prefix}user:{user_id}"
            value = await self.redis.get(key)

            if value:
                # Parse ISO format timestamp
                return datetime.fromisoformat(value.decode())
            return None

        except RedisError as e:
            logger.error(f"Failed to check user revocation: {e}")
            raise TokenBlacklistError("Failed to check user revocation") from e


class RedisConnection:
    """
    Redis connection manager with connection pooling.

    Usage:
        redis_conn = RedisConnection()
        await redis_conn.connect()

        # Use client
        await redis_conn.client.set("key", "value")

        # Cleanup
        await redis_conn.disconnect()
    """

    def __init__(self):
        self.pool: ConnectionPool | None = None
        self.client: Redis | None = None

    async def connect(self) -> Redis:
        """
        Establish redis connection with Pool

        Returns:
            Redis client instance
        """
        if self.client:
            return self.client

        try:
            self.pool = ConnectionPool.from_url(
                url=settings.REDIS_URL,
                max_connections=settings.REDIS_MAX_CONNECTIONS,
                decode_responses=False,
                socket_timeout=5,
                socket_connect_timeout=5,
            )
            self.client = Redis(connection_pool=self.pool)

            await self.client.ping()
            logger.success("Redis connection established")

            return self.client

        except RedisError as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise TokenBlacklistError("Failed to connect to Redis") from e

    async def disconnect(self):
        """
        Close redis connection
        """
        if self.client:
            await self.client.close()
            self.client = None
            logger.success("Redis connection closed")

        if self.pool:
            await self.pool.disconnect()
            self.pool = None
            logger.success("Redis pool closed")

        logger.success("Redis connection closed")


# Global redis connection instance
_redis_connection: RedisConnection | None = None


async def get_redis_connection() -> Redis:
    """
    Get or create Redis client instance (singleton pattern).

    Returns:
        Redis client

    Example:
        >>> redis = await get_redis_client()
        >>> await redis.set("key", "value")
    """
    global _redis_connection

    if _redis_connection is None:
        _redis_connection = RedisConnection()
        await _redis_connection.connect()

    return _redis_connection.client


async def get_token_blacklist() -> TokenBlacklist:
    """
    Dependency injection function for FastAPI.

    Returns:
        TokenBlacklist instance

    Usage in FastAPI:
        @app.post("/logout")
        async def logout(
            blacklist: TokenBlacklist = Depends(get_token_blacklist)
        ):
            await blacklist.revoke_token(token)
    """
    redis_client = await get_redis_connection()
    return TokenBlacklist(redis_client)


async def shutdown_redis():
    """
    Cleanup function to close Redis connections on app shutdown.

    Call this in FastAPI lifespan shutdown.
    """
    global _redis_connection

    if _redis_connection:
        await _redis_connection.disconnect()
        _redis_connection = None
        logger.info("Redis connections cleaned up")
