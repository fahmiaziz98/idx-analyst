from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from src.auth.oauth import get_user_info, is_admin_email, oauth
from src.core.exception import AuthServiceError
from src.database.models import User, UserRole
from src.repositories.user_repository import UserRepository


class AuthService:
    """
    Handle authentication business logic, specifically focusing on OAuth flows
    and user account provisioning.
    """

    def __init__(self, db: AsyncSession):
        """
        Initialize the AuthService with a database session.

        Args:
            db: Asynchronous database session.
        """
        self.user_repo = UserRepository(db)

    async def handle_google_callback(self, request: Request) -> User:
        """
        Complete the Google OAuth callback flow by exchanging the authorization
        code for user information and managing the local user record.

        Args:
            request: The incoming starlette/fastapi request containing OAuth data.

        Returns:
            The local User record (either retrieved or newly created).

        Raises:
            AuthServiceError: If any part of the OAuth flow or user creation fails.
        """
        try:
            # 1. Exchange authorization code for access token
            logger.info("Exchanging Google authorization code for access token.")
            token = await oauth.google.authorize_access_token(request)

            # 2. Retrieve user identity information from Google
            user_info = await get_user_info(token)
            if not user_info:
                raise AuthServiceError("Failed to retrieve user information from Google.")

            email = user_info.get("email")
            if not email:
                raise AuthServiceError("Google account did not provide an email address.")

            name = user_info.get("name", email.split("@")[0])
            avatar_url = user_info.get("picture")

            # 3. Synchronize with local user database
            user = await self.user_repo.get_by_email(email)

            if user:
                logger.info(f"Existing user logged in: {email}")
                user = await self.user_repo.update(user, name=name, avatar_url=avatar_url)
            else:
                logger.info(f"Provisioning new user account: {email}")
                role = UserRole.ADMIN if is_admin_email(email) else UserRole.USER
                user = await self.user_repo.create(
                    email=email, name=name, avatar_url=avatar_url, role=role
                )

            return user

        except AuthServiceError:
            # Re-raise known service errors
            raise
        except Exception as e:
            logger.error(f"Unexpected error during Google authentication: {str(e)}")
            raise AuthServiceError("An unexpected error occurred during authentication.") from e
