from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.jwt import verify_token
from src.database.models import User, UserRole
from src.database.session import get_db

# ===== Security Scheme =====
# HTTPBearer: expect "Authorization: Bearer <token>" header
security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Get current authenticated user from JWT token.

    Flow:
    1. Extract token from Authorization header
    2. Verify & decode token
    3. Get user from database
    4. Return user object

    Args:
        credentials: HTTP Bearer credentials (automatically extracted by FastAPI)
        db: Database session

    Returns:
        User object

    Raises:
        HTTPException 401: Token invalid/expired or user not found

    """
    token = credentials.credentials

    token_data = verify_token(token)
    if not token_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Get user from database
    result = await db.execute(select(User).where(User.id == token_data.user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Update last_login (optional, for tracking)
    # Note: this will trigger a database write on every request
    # If traffic is high, consider updating less frequently
    # from datetime import datetime
    # user.last_login = datetime.utcnow()
    # await db.commit()

    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    """
    Require admin role.

    This dependency chains with get_current_user,
    so it will verify the token first, then check admin role.

    Args:
        user: Current user (from get_current_user dependency)

    Returns:
        User object (confirmed to be admin)

    Raises:
        HTTPException 403: User is not admin

    """
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required. You are not authorized to perform this action.",
        )

    return user


async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(
        HTTPBearer(auto_error=False)  # auto_error=False: don't raise exception if no token
    ),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """
    Get current user (optional).

    This dependency is similar to get_current_user, but doesn't require token.
    Useful for endpoints that can be accessed with or without auth.

    Args:
        credentials: HTTP Bearer credentials (optional)
        db: Database session

    Returns:
        User object if authenticated, None otherwise
    """
    if not credentials:
        return None

    # Verify token
    token_data = verify_token(credentials.credentials)
    if not token_data:
        return None

    # Get user
    result = await db.execute(select(User).where(User.id == token_data.user_id))
    return result.scalar_one_or_none()


def check_user_owns_resource(user: User, resource_user_id: str) -> bool:
    """
    Helper function to check ownership.

    Used to verify that a user can only access/modify
    their own resources.

    Args:
        user: Current user
        resource_user_id: User ID that owns the resource

    Returns:
        True if user owns resource or user is admin

    """
    # Admin can access all resources
    if user.role == UserRole.ADMIN:
        return True

    # User can only access their own resources
    return user.id == resource_user_id
