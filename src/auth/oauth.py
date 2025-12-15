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
        "timeout": 30,
    },
)


async def get_user_info(token: dict) -> dict | None:
    """
    Get user info from Google using access token.

    User info we receive:
    - email: user email address
    - name: full name
    - picture: profile picture URL
    - sub: Google user ID (unique identifier)

    Args:
        token: Token response 

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
