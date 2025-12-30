import secrets
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependency import get_current_user
from src.auth.jwt import create_token_pair, get_token_remaining_seconds, verify_token
from src.auth.oauth import oauth
from src.auth.token_blacklist import TokenBlacklist, get_token_blacklist
from src.core.config import settings
from src.database.models import User
from src.database.session import get_db
from src.services.auth_service import AuthService

router = APIRouter()


def validate_redirect_url(url: str):
    """
    Validate redirect URL against whitelist.

    Security checks:
    1. URL must use HTTPS in production
    2. Domain must be in ALLOWED_REDIRECT_DOMAINS
    3. No open redirect vulnerability

    Args:
        url: Redirect URL to validate

    Returns:
        True if valid, False otherwise
    """
    if not url:
        return True

    try:
        parsed = urlparse(url)
        logger.info(f"Validating redirect URL: {url}")
        logger.info(f"Parsed redirect URL: {parsed}")

        # Check if URL uses HTTPS in production
        if settings.is_production and parsed.scheme != "https":
            logger.warning(f"Invalid redirect URL scheme in production: {parsed.scheme}")
            return False

        if parsed.scheme not in ("http", "https"):
            logger.warning(f"Invalid redirect URL scheme: {parsed.scheme}")
            return False

        # Extract domain (remove port if present)
        domain = parsed.netloc.split(":")[0] if parsed.netloc else ""

        # Check against whitelist
        if domain not in settings.ALLOWED_REDIRECT_DOMAINS:
            logger.warning(f"Redirect domain not in whitelist: {domain}")
            return False

        return True
    except ValueError:
        logger.warning(f"Invalid redirect URL: {url}")
        return False


def generate_state_token() -> str:
    """
    Generate cryptographically secure state token for CSRF protection.

    Returns:
        State token
    """
    return secrets.token_urlsafe(32)


# ===== Login =====
@router.get("/login")
async def login(
    request: Request,
    redirect_url: str | None = Query(
        None,
        description="URL redirect after login",
        max_length=500,
    ),
):
    """
    Initiate Google OAuth login flow with CSRF protection.

    Flow:
    1. Validate redirect URL against whitelist
    2. Generate state parameter for CSRF protection
    3. Store state and redirect URL in session
    4. Redirect user to Google consent screen

    Query Parameters:
        redirect_url: Optional URL to redirect after login (must be whitelisted)

    Returns:
        Redirect to Google OAuth consent page

    Raises:
        HTTPException 400: If redirect URL is invalid

    Example:
        GET /auth/login?redirect_url=https://app.example.com/dashboard
    """

    # Validate redirect URL against whitelist
    if redirect_url and not validate_redirect_url(redirect_url):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid redirect URL",
        )

    # Generate state parameter for CSRF protection
    # Store state and redirect URL in session
    state = generate_state_token()
    request.session["oauth_state"] = state
    request.session["redirect_url"] = redirect_url or settings.FRONTEND_URL

    # Redirect user to Google consent screen
    callback_uri = str(request.url_for("oauth_callback"))
    return await oauth.google.authorize_redirect(
        request,
        callback_uri,
        state=state,
    )


# ===== OAuth Callback =====
@router.get("/callback")
async def oauth_callback(
    request: Request,
    state: str = Query(..., description="State parameter from google"),
    code: str = Query(..., description="Authorization code from google"),
    db: AsyncSession = Depends(get_db),
):
    """
    Handle OAuth callback from Google with security validations.

    Security Flow:
    1. Verify state parameter matches (CSRF protection)
    2. Exchange authorization code for access token
    3. Get user info from Google
    4. Create or update user in database
    5. Generate JWT tokens
    6. Set secure HTTP-only cookies
    7. Redirect to original destination

    Query Parameters:
        state: CSRF token (must match session)
        code: Authorization code from Google

    Returns:
        Redirect to frontend with secure cookies set

    Raises:
        HTTPException 400: Invalid state parameter (CSRF attempt)
        HTTPException 500: Authentication failed

    Example:
        GET /auth/callback?state=abc123&code=xyz789
    """
    try:
        # 1. Verify state parameter matches (CSRF protection)
        stored_state = request.session.get("oauth_state")
        if not stored_state or state != stored_state:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid state parameter",
            )

        # 2. Clear state parameter from session
        request.session.pop("oauth_state", None)

        # 3. Handle Oauth callback via auth service
        auth_service = AuthService(db)
        user = await auth_service.handle_google_callback(request)

        # 4. Generate JWT tokens
        token = create_token_pair(
            user_id=user.id,
            role=user.role.value,
            email=user.email,
        )

        # 5. Get redirect url from session
        redirect_url = request.session.pop("redirect_url", settings.FRONTEND_URL)

        # ===== FIXED: Pass token to Streamlit via URL parameter =====
        # This is required because Streamlit cannot read httponly cookies
        # For production React app, remove this and use httponly cookies only
        # separator = "&" if "?" in redirect_url else "?"
        # redirect_url_with_token = (
        #     f"{redirect_url}{separator}"
        #     f"token={token.access_token}&"
        #     f"refresh_token={token.refresh_token}"
        # )

        # 6. Set secure HTTP-only cookies
        response = RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)

        # Set access token cookie (HTTP-only, secure in production)
        response.set_cookie(
            key="access_token",
            value=token.access_token,
            httponly=True,  # Prevent JavaScript access
            secure=settings.COOKIE_SECURE,  # HTTPS only in production
            samesite=settings.COOKIE_SAMESITE,  # CSRF protection
            # domain=security_settings.COOKIE_DOMAIN,
            max_age=settings.jwt_access_token_expire_seconds,
            path="/",
        )

        # Set refresh token cookie (HTTP-only, secure in production)
        response.set_cookie(
            key="refresh_token",
            value=token.refresh_token,
            httponly=True,
            secure=settings.COOKIE_SECURE,
            samesite=settings.COOKIE_SAMESITE,
            # domain=security_settings.COOKIE_DOMAIN,
            max_age=settings.jwt_refresh_token_expire_seconds,  # 30 days, not 3 minutes!
            path="/api/v1/auth",  # Restrict to auth endpoints only
        )

        logger.success(f"User {user.email} logged in successfully")

        return response

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"OAuth callback error: {e}")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Authentication failed: {str(e)}",
        ) from e


# ===== Refresh Token =====
@router.post("/refresh")
async def refresh_access_token(
    request: Request,
    response: Response,
    # user: User = Depends(get_current_user),
    blacklist: TokenBlacklist = Depends(get_token_blacklist),
):
    """
    Refresh access token using refresh token.

    This endpoint allows clients to obtain a new access token without re-authenticating
    when the current access token expires. This provides better UX.

    Flow:
    1. Extract refresh token from cookie or Authorization header
    2. Verify refresh token (signature, expiration, not blacklisted)
    3. Generate new access token
    4. Optionally rotate refresh token (security best practice)
    5. Blacklist old tokens
    6. Return new tokens

    Request:
        Cookie: refresh_token=<token> OR
        Authorization: Bearer <refresh_token>

    Returns:
        {
            "access_token": "new_access_token",
            "token_type": "bearer",
            "expires_in": 900
        }

    Raises:
        HTTPException 401: Refresh token invalid, expired, or revoked
        HTTPException 500: Token refresh failed

    Example:
        POST /auth/refresh
        Cookie: refresh_token=eyJ...
        
        Response:
        {
            "access_token": "eyJhbGc...",
            "token_type": "bearer",
            "expires_in": 900
        }
    """
    try:
        # Extract refresh token from cookie or header
        refresh_token = request.cookies.get("refresh_token")

        if not refresh_token:
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                refresh_token = auth_header.split("Bearer ")[1]

        if not refresh_token:
            logger.warning("Refresh attempt failed: No refresh token found in cookies or headers")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token not found",
                headers={"WWW-Authenticate": "Bearer"},
            )

        logger.info("Attempting to verify refresh token...")

        # Verify refresh token
        token_data = verify_token(refresh_token, token_type="refresh")
        if not token_data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Check if refresh token is blacklist
        if await blacklist.is_revoked(refresh_token):
            logger.warning("Refresh attempt failed: Token is blacklisted (revoked)")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token revoked",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        logger.info(f"Refresh token verified for user_id: {token_data.user_id}")
        
        # Check if user all token have been revoked
        user_revoked_at = await blacklist.is_user_revoked(token_data.user_id)
        if user_revoked_at:
            if token_data.issued_at and token_data.issued_at < user_revoked_at:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="All user tokens revoked. Please login again.",
                    headers={"WWW-Authenticate": "Bearer"},
                )

        # 5. Get user info (we need role and email for new access token)
        # In production, you should fetch this from database
        # For now, we trust the data in the refresh token
        from sqlalchemy import select

        from src.database.session import get_db
        
        async for db in get_db():
            result = await db.execute(
                select(User).where(User.id == token_data.user_id)
            )
            user = result.scalar_one_or_none()
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User not found",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            
            # 6. Generate token rotation
            logger.info(f"Generating new token pair for user {user.email}")
            new_tokens = create_token_pair(
                user_id=user.id,
                role=user.role,
                email=user.email,
            )

            # 7. Blacklist old refresh token
            remaining = get_token_remaining_seconds(refresh_token)
            if remaining:
                await blacklist.add(refresh_token, remaining)
                logger.info(f"Old refresh token blacklisted for user {user.email}")
            
            # 8. Set new cookies
            response.set_cookie(
                key="access_token",
                value=new_tokens.access_token,
                httponly=True,
                secure=settings.COOKIE_SECURE,
                samesite=settings.COOKIE_SAMESITE,
                max_age=settings.jwt_access_token_expire_seconds,
                path="/",
            )
            
            response.set_cookie(
                key="refresh_token",
                value=new_tokens.refresh_token,
                httponly=True,
                secure=settings.COOKIE_SECURE,
                samesite=settings.COOKIE_SAMESITE,
                max_age=settings.jwt_refresh_token_expire_seconds,
                path="/api/v1/auth",
            )
            
            logger.success(f"Tokens refreshed for user {user.email}")
            
            # 9. Return new access token (for clients that don't use cookies)
            return {
                "access_token": new_tokens.access_token,
                "token_type": "bearer",
                "expires_in": settings.jwt_access_token_expire_seconds,
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token refresh error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token refresh failed",
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
async def logout(
    request: Request,
    user: User = Depends(get_current_user),
    blacklist: TokenBlacklist = Depends(get_token_blacklist),
):
    """
    Logout user and revoke tokens.

    Flow:
    1. Extract tokens from cookies
    2. Add tokens to blacklist
    3. Clear cookies
    4. Return success response

    Headers/Cookies:
        Authorization: Bearer <token> OR Cookie: access_token=<token>
        Cookie: refresh_token=<token>

    Returns:
        Success message

    Example:
        POST /auth/logout
        Cookie: access_token=...; refresh_token=...
    """
    try:
        access_token = request.cookies.get("access_token")
        refresh_token = request.cookies.get("refresh_token")

        # Revoke access token if present
        if access_token:
            remaining = get_token_remaining_seconds(access_token)
            if remaining:
                await blacklist.revoke_token(access_token, remaining)
                logger.info(f"Access token revoked for user {user.email}")
            else:
                logger.info(f"Access token expired for user {user.email}")

        # Revoke refresh token if present
        if refresh_token:
            remaining = get_token_remaining_seconds(refresh_token)
            if remaining:
                await blacklist.revoke_token(refresh_token, remaining)
                logger.info(f"Refresh token revoked for user {user.email}")
            else:
                logger.info(f"Refresh token expired for user {user.email}")

        response = RedirectResponse(url=settings.FRONTEND_URL, status_code=status.HTTP_302_FOUND)

        # Clear cookies
        response.delete_cookie(
            key="access_token",
            # domain=settings.COOKIE_DOMAIN,
            path="/",
        )

        response.delete_cookie(
            key="refresh_token",
            # domain=settings.COOKIE_DOMAIN,
            path="/api/v1/auth",
        )

        logger.success(f"User {user.email} logged out successfully")

        return response
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Logout error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Logout failed",
        ) from e


@router.post("/revoke-all")
async def revoke_all_tokens(
    user: User = Depends(get_current_user),
    blacklist: TokenBlacklist = Depends(get_token_blacklist),
):
    """
    Revoke all tokens for current user (security feature).

    Use cases:
    - Password reset
    - Account compromise
    - Logout from all devices

    Returns:
        Success message
    """
    await blacklist.revoke_all_user_tokens(
        user_id=user.id, expiry_seconds=settings.jwt_refresh_token_expire_seconds
    )

    logger.warning(f"All tokens revoked for user {user.email}")

    return {"message": "All tokens revoked successfully", "user_id": user.id}
