from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.jwt import verify_token
from src.auth.token_blacklist import TokenBlacklist, get_token_blacklist
from src.database.models import User, UserRole
from src.database.session import get_db

# ===== Security Scheme =====
# HTTPBearer: expect "Authorization: Bearer <token>" header
security = HTTPBearer(auto_error=False)


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


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
    blacklist: TokenBlacklist = Depends(get_token_blacklist),
    token: str | None = Depends(get_token_from_request),
) -> User:
    """
    Get current authenticated user from JWT token with blacklist checking.

    Security Flow:
    1. Extract token from Authorization header or cookie
    2. Verify and decode token
    3. Check if token is in blacklist (revoked)
    4. Check if user's all tokens have been revoked
    5. Get user from database
    6. Return user object

    Args:
        request: FastAPI request
        db: Database session
        blacklist: Token blacklist service
        token: JWT token (from header or cookie)

    Returns:
        User object

    Raises:
        HTTPException 401: Token invalid, expired, revoked, or user not found

    Example:
        @app.get("/protected")
        async def protected_route(user: User = Depends(get_current_user)):
            return {"user_id": user.id}
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

    def wrapper(user: User = Depends(get_current_user)) -> User:
        if user.role != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Role access required. You are not authorized to perform this action.",
            )
        return user

    return wrapper
