from authlib.integrations.starlette_client import OAuth
from loguru import logger

from src.core.config import settings

oauth = OAuth()

oauth.register(
    name="google",
    client_id=settings.GOOGLE_CLIENT_ID,
    client_secret=settings.GOOGLE_CLIENT_SECRET,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={
        "scope": "openid email profile",
        "redirect_uri": "http://localhost:7860/auth/callback",
        "timeout": 10,
    },
)


async def get_google_login_url(redirect_uri: str) -> str:
    """
    Generate Google OAuth authorization URL.

    This URL will redirect the user to Google's consent screen.

    Args:
        redirect_uri: Callback URL after authorization

    Returns:
        Google authorization URL

    """
    return await oauth.google.authorize_redirect_url(redirect_uri)


async def exchange_code_for_token(code: str, redirect_uri: str) -> dict | None:
    """
    Exchange authorization code for access token.

    After user authorizes, Google will redirect to callback
    with an authorization code. We exchange this code for
    an access token that can be used to get user info.

    Args:
        code: Authorization code from Google
        redirect_uri: Same redirect_uri used during authorization

    Returns:
        Token response (dict) with access_token, id_token, etc.
        None if error

    """
    try:
        token = await oauth.google.authorize_access_token(code=code, redirect_uri=redirect_uri)
        return token
    except Exception as e:
        logger.error(f"Error exchanging code for token: {e}")
        return None


async def get_user_info(token: dict) -> dict | None:
    """
    Get user info from Google using access token.

    User info we receive:
    - email: user email address
    - name: full name
    - picture: profile picture URL
    - sub: Google user ID (unique identifier)

    Args:
        token: Token response from exchange_code_for_token

    Returns:
        User info (dict) or None if error
    """
    try:
        user_info = token.get("userinfo")

        if not user_info:
            resp = await oauth.google.get(
                "https://www.googleapis.com/oauth2/v3/userinfo", token=token
            )
            user_info = resp.json()

        return user_info

    except Exception as e:
        print(f"Error getting user info: {e}")
        return None


def is_admin_email(email: str) -> bool:
    """
    Check if email belongs to an admin.

    Simple check: compare with ADMIN_EMAIL in settings.

    Args:
        email: User email

    Returns:
        True if admin, False if regular user
    """
    return email.lower() == settings.ADMIN_EMAIL.lower()


# ===== Helper for Testing =====
async def test_oauth_connection() -> bool:
    """
    Test OAuth configuration.

    Useful for verifying credentials are valid before deployment.

    Returns:
        True if config is valid, False if error
    """
    try:
        # Check if credentials are set
        if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
            return False

        # Try to get server metadata
        metadata = await oauth.google.load_server_metadata()
        return metadata is not None

    except Exception as e:
        print(f"OAuth configuration test failed: {e}")
        return False
