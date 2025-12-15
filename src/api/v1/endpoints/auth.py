import traceback
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependency import get_current_user
from src.auth.jwt import create_access_token
from src.auth.oauth import get_user_info, is_admin_email, oauth
from src.core.config import settings
from src.database.models import User, UserRole
from src.database.session import get_db

router = APIRouter()


# login
@router.get("/login")
async def login(
    request: Request,
    redirect_url: str | None = Query(None, description="URL redirect after login"),
):
    """
    Initiate Google Oauth login flow

    Flow:
    - Generate Google authorization URL
    - Redirect user to google consent screen

    Query params:
        redirect_url: Optional url redirect after successfully login
    """
    callback_uri = str(request.url_for("oauth_callback"))
    return await oauth.google.authorize_redirect(request, callback_uri)


@router.get("/callback")
async def oauth_callback(
    request: Request,
    code: str = Query(..., description="Authorization code from google"),
    db: AsyncSession = Depends(get_db),
):
    """
    Handle OAuth callback from Google

    Flow:
    - Exchange authorization code for access token
    - Get user info from Google
    - Check if user exists
    - Create or update user
    - Create JWT token
    - Redirect to frontend

    Query params:
        code: Authorization code from google
    """
    try:
        try:
            token = await oauth.google.authorize_access_token(request)
        except Exception as token_error:
            logger.error(f"Failed to exchange code for token: {token_error}")
            logger.error(f"Traceback: {traceback.format_exc()}")

            if "Name or service not known" in str(token_error):
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Cannot reach Google OAuth servers. Check your internet connection or DNS settings.",
                )
            raise

        # Get user info
        try:
            user_info = await get_user_info(token)
        except Exception as info_error:
            logger.error(f"Failed to get user info: {info_error}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to get user info from Google: {str(info_error)}",
            )

        if not user_info:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to get user info from Google",
            )

        email = user_info.get("email")
        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Email not provided by Google"
            )

        name = user_info.get("name", email.split("@")[0])
        avatar_url = user_info.get("picture")

        # Check if user exists
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if user:
            # Update existing user
            user.name = name
            user.avatar_url = avatar_url
            user.last_login = datetime.now(UTC)
            await db.commit()
            await db.refresh(user)
        else:
            # Create new user
            role = UserRole.ADMIN if is_admin_email(email) else UserRole.USER
            user = User(
                email=email,
                name=name,
                avatar_url=avatar_url,
                last_login=datetime.now(UTC),
                role=role,
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)

        # Create JWT token
        jwt_token = create_access_token(user_id=user.id, role=user.role.value, email=user.email)

        # Redirect to frontend
        frontend_url = "http://localhost:8501"
        redirect_url = f"{frontend_url}?token={jwt_token}"

        return RedirectResponse(url=redirect_url)

    except HTTPException:
        raise
    except Exception as e:
        # ✅ Detailed error logging
        logger.error(f"OAuth callback error: {e}")
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Traceback: {traceback.format_exc()}")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Authentication failed: {str(e)}",
        )


# ===== Get Current User =====
@router.get("/me")
async def get_me(user: User = Depends(get_current_user)):
    """
    Get current authenticated user info.

    Endpoint ini require valid JWT token di Authorization header.

    Headers:
        Authorization: Bearer <jwt_token>

    Returns:
        User info (email, name, role, etc)

    Example:
        GET /auth/me
        Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

        Response:
        {
            "id": "user-123",
            "email": "user@example.com",
            "name": "John Doe",
            "role": "user",
            "avatar_url": "https://...",
            "last_login": "2024-01-01T10:00:00"
        }
    """
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "role": user.role.value,
        "avatar_url": user.avatar_url,
        "last_login": user.last_login,
        "created_at": user.created_at,
    }


# ===== Logout =====
@router.post("/logout")
async def logout(user: User = Depends(get_current_user)):
    """
    Logout user.

    Note: JWT tokens adalah stateless, jadi tidak bisa di-"revoke" dari server.
    Logout hanya perlu client-side delete token dari localStorage/cookie.

    Endpoint ini optional, tapi berguna untuk:
    - Update last_login timestamp
    - Log logout event
    - Clear server-side session (jika ada)

    Returns:
        Success message

    Example:
        POST /auth/logout
        Authorization: Bearer <token>

        Response:
        {
            "message": "Logged out successfully"
        }
    """
    return {"message": "Logged out successfully", "email": user.email}


# ===== Health Check =====
@router.get("/health")
async def auth_health():
    """
    Health check untuk authentication system.

    Check:
    - OAuth credentials configured
    - JWT secret configured

    Returns:
        Health status

    Example:
        GET /auth/health

        Response:
        {
            "status": "healthy",
            "oauth_configured": true,
            "jwt_configured": true
        }
    """
    oauth_configured = bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET)
    jwt_configured = bool(settings.JWT_SECRET and len(settings.JWT_SECRET) >= 32)

    is_healthy = oauth_configured and jwt_configured

    return {
        "status": "healthy" if is_healthy else "unhealthy",
        "oauth_configured": oauth_configured,
        "jwt_configured": jwt_configured,
        "admin_email_set": bool(settings.ADMIN_EMAIL),
    }
