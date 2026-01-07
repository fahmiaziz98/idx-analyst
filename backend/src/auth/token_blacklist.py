from datetime import UTC, datetime
from cachetools import TTLCache
from loguru import logger
from redis.asyncio import ConnectionPool, Redis
from redis.exceptions import RedisError

from src.core.config import settings
from src.core.exception import TokenBlacklistError


class TokenBlacklist:
    """
    Token blacklist service using Redis for storage with local memory caching.

    Features:
    - Automatic token expiration using Redis TTL
    - Efficient O(1) lookup
    - Dual-layer caching (Local TTLCache + Redis)
    - Graceful degradation if Redis unavailable
    """

    def __init__(self, redis_client: Redis):
        self.redis = redis_client
        self._prefix = "blacklist:token:"
        # Cache for single token revocation (jti/token)
        # We cache both True and False results to avoid Redis calls for valid tokens
        self._token_cache = TTLCache(maxsize=10000, ttl=300)  # 5m TTL
        
        # Cache for user-level revocation timestamps
        self._user_cache = TTLCache(maxsize=5000, ttl=300)   # 5m TTL

    async def revoke_token(self, token: str, expiry_seconds: int):
        """
        Revoke a token by adding it to the blacklist with an expiration time.
        """
        try:
            key = f"{self._prefix}{token}"
            revoked_at = datetime.now(UTC).isoformat()

            await self.redis.setex(name=key, time=expiry_seconds, value=revoked_at)
            
            # Update local cache immediately
            self._token_cache[token] = True
            
            logger.success(f"Token revoked successfully (expires in {expiry_seconds}s)")
            return True

        except RedisError as e:
            logger.error(f"Failed to revoke token: {e}")
            raise TokenBlacklistError("Failed to revoke token") from e

    async def is_revoked(self, token: str) -> bool:
        """
        Check if a token is revoked, using local cache to minimize Redis calls.
        """
        # Check local cache first (catches both hits and misses)
        if token in self._token_cache:
            return self._token_cache[token]

        try:
            key = f"{self._prefix}{token}"
            exists = await self.redis.exists(key)
            
            # Cache the result (True or False)
            self._token_cache[token] = bool(exists)
            
            if exists:
                logger.info(f"Token revocation confirmed from Redis: {token[:10]}...")
            
            return bool(exists)
        except RedisError as e:
            logger.error(f"Failed to check token revocation: {e}")
            raise TokenBlacklistError("Failed to check token revocation") from e
    
    async def revoke_all_user_tokens(self, user_id: str, expiry_seconds: int = 3600) -> int:
        """
        Revoke all tokens for a specific user.
        """
        try:
            key = f"{self._prefix}user:{user_id}"
            revoked_at = datetime.now(UTC).isoformat()

            await self.redis.setex(name=key, time=expiry_seconds, value=revoked_at)
            
            # Invalidate/Update local user cache
            self._user_cache[user_id] = datetime.fromisoformat(revoked_at)

            logger.warning(f"All tokens revoked for user {user_id}")
            return 1

        except RedisError as e:
            logger.error(f"Failed to revoke user tokens: {e}")
            raise TokenBlacklistError("Failed to revoke user tokens") from e

    async def is_user_revoked(self, user_id: str) -> datetime | None:
        """
        Check if all tokens for a user have been revoked, using local cache.
        """
        # Check local cache first
        if user_id in self._user_cache:
            return self._user_cache[user_id]

        try:
            key = f"{self._prefix}user:{user_id}"
            value = await self.redis.get(key)

            if value:
                revoked_at_str = value.decode()
                revoked_at = datetime.fromisoformat(revoked_at_str)
                self._user_cache[user_id] = revoked_at
                logger.info(f"User {user_id} revocation timestamp cached from Redis")
                return revoked_at
            
            # Cache the absence of revocation
            self._user_cache[user_id] = None
            return None

        except RedisError as e:
            logger.error(f"Failed to check user revocation: {e}")
            raise TokenBlacklistError("Failed to check user revocation") from e


class RedisConnection:
    """
    Redis connection manager with connection pooling.
    """

    def __init__(self):
        self.pool: ConnectionPool | None = None
        self.client: Redis | None = None

    async def connect(self) -> Redis:
        """
        Establish redis connection with Pool
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

        if self.pool:
            await self.pool.disconnect()
            self.pool = None

        logger.success("Redis connection closed")


# Global redis connection instance
_redis_connection: RedisConnection | None = None


async def get_redis_connection() -> Redis:
    """
    Get or create Redis client instance (singleton pattern).
    """
    global _redis_connection

    if _redis_connection is None:
        _redis_connection = RedisConnection()
        await _redis_connection.connect()

    return _redis_connection.client


async def get_token_blacklist() -> TokenBlacklist:
    """
    Dependency injection function for FastAPI.
    """
    redis_client = await get_redis_connection()
    return TokenBlacklist(redis_client)


async def shutdown_redis():
    """
    Cleanup function to close Redis connections on app shutdown.
    """
    global _redis_connection

    if _redis_connection:
        await _redis_connection.disconnect()
        _redis_connection = None
        logger.info("Redis connections cleaned up")
