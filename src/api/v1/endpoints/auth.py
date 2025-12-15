import traceback

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependency import get_current_user
from src.auth.oauth import oauth
from src.core.config import settings
from src.database.models import User
from src.database.session import get_db
from src.services.auth_service import AuthService

router = APIRouter()


# ===== Login =====
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


# ===== OAuth Callback =====
@router.get("/callback")
async def oauth_callback(
    request: Request,
    code: str = Query(..., description="Authorization code from google"),
    db: AsyncSession = Depends(get_db),
):
    """
    Handle OAuth callback from Google
    
    Delegates to AuthService.
    """
    try:
        auth_service = AuthService(db)
        redirect_url = await auth_service.handle_google_callback(request)
        return RedirectResponse(url=redirect_url)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OAuth callback error: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Authentication failed: {str(e)}",
        ) from e


# ===== Get Current User =====
@router.get("/me")
async def get_me(user: User = Depends(get_current_user)):
    """
    Get current authenticated user info.

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

    Note: JWT tokens are stateless, so they cannot be "revoked" from the server.
    Logout only requires client-side deletion of the token from localStorage/cookie.

    This endpoint is optional, but useful for:
    - Updating last_login timestamp
    - Logging logout events
    - Clearing server-side sessions (if any)

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
