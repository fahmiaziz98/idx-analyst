import json
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from src.auth.jwt import verify_token
from src.auth.token_blacklist import TokenBlacklist, get_token_blacklist, get_redis_connection
from src.database.models import User, UserRole
from src.database.session import get_db
from src.services.conversation_service import ConversationService
from src.services.messages_service import MessageService


# ===== Security Scheme =====
# HTTPBearer: expect "Authorization: Bearer <token>" header
security = HTTPBearer(auto_error=False)


async def get_conversation_service(
    db: AsyncSession = Depends(get_db),
) -> ConversationService:
    """
    Dependency to get ConversationService instance with active db session.
    """
    return ConversationService(db)


async def get_message_service(
    db: AsyncSession = Depends(get_db),
) -> MessageService:
    """
    Dependency to get MessageService instance with active db session.
    """
    return MessageService(db)


async def get_token_from_request(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> str | None:
    """
    Extract JWT token from request (Authorization header OR cookies).

    Priority:
    1. Authorization header (Bearer token)
    2. access_token cookie

    Args:
        request: FastAPI request object
        credentials: Optional Authorization header credentials

    Returns:
        Token string or None if not found
    """
    if credentials and credentials.credentials:
        return credentials.credentials

    # Fallback to cookie
    token = request.cookies.get("access_token")
    if token:
        return token

    return None


class StatelessUser:
    """Minimal user-like object reconstructed from JWT payload."""
    def __init__(self, id: str, email: str, role: UserRole, name: str = None, avatar_url: str = None):
        self.id = id
        self.email = email
        self.role = role
        self.name = name or email.split("@")[0]
        self.avatar_url = avatar_url
    
    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN


async def get_current_user(
    request: Request,
    blacklist: TokenBlacklist = Depends(get_token_blacklist),
    token: str | None = Depends(get_token_from_request),
) -> StatelessUser:
    """
    Get current authenticated user from JWT token without database lookup (Stateless).
    """
    # Check if token is present
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not Authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify token
    token_data = verify_token(token, token_type="access")
    if not token_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if token is in blacklist
    if await blacklist.is_revoked(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if all user tokens have been revoked
    user_revoked_at = await blacklist.is_user_revoked(token_data.user_id)
    if user_revoked_at:
        if token_data.issued_at and token_data.issued_at < user_revoked_at:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="All user tokens revoked. Please login again.",
                headers={"WWW-Authenticate": "Bearer"},
            )

    # Return stateless user reconstructed from token claims
    return StatelessUser(
        id=token_data.user_id,
        email=token_data.email,
        role=UserRole(token_data.role)
    )


async def get_current_user_full(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: StatelessUser = Depends(get_current_user),
) -> User:
    """
    Get full user object with Redis caching.
    """
    redis = await get_redis_connection()
    cache_key = f"user:cache:{user.id}"
    
    try:
        cached_user = await redis.get(cache_key)
        if cached_user:
            user_data = json.loads(cached_user)
            # Create a detached User object
            return User(
                id=user_data["id"],
                email=user_data["email"],
                name=user_data["name"],
                role=UserRole(user_data["role"]),
                avatar_url=user_data.get("avatar_url")
            )
    except Exception as e:
        logger.warning(f"User cache hit failed: {e}")

    # Cache miss or error, fetch from DB
    result = await db.execute(select(User).where(User.id == user.id))
    full_user = result.scalar_one_or_none()
 
    if not full_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Store in Redis
    try:
        user_dict = {
            "id": full_user.id,
            "email": full_user.email,
            "name": full_user.name,
            "role": full_user.role.value if hasattr(full_user.role, "value") else full_user.role,
            "avatar_url": full_user.avatar_url
        }
        await redis.setex(cache_key, 900, json.dumps(user_dict))
    except Exception as e:
        logger.warning(f"Failed to cache user: {e}")

    return full_user


async def require_admin(user: StatelessUser = Depends(get_current_user)) -> StatelessUser:
    """
    Require admin role for endpoint access.

    This dependency chains with get_current_user, so it will:
    1. Verify the token first
    2. Get the user
    3. Check admin role

    Args:
        user: Current user (from get_current_user dependency)

    Returns:
        User object (confirmed to be admin)

    Raises:
        HTTPException 403: User is not admin

    Example:
        @app.delete("/admin/users/{user_id}")
        async def delete_user(
            user_id: str,
            admin: User = Depends(require_admin)
        ):
            # Only admins can reach here
            pass
    """
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required. You are not authorized to perform this action.",
        )

    return user


async def require_role(required_role: UserRole):
    """
    Factory function to create role-based dependency.

    Args:
        required_role: The role required for access

    Returns:
        Dependency function that checks for the role
    """

    def wrapper(user: StatelessUser = Depends(get_current_user)) -> StatelessUser:
        if user.role != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Role access required. You are not authorized to perform this action.",
            )
        return user

    return wrapper
