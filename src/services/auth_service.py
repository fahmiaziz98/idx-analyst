
from fastapi import HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.jwt import create_access_token
from src.auth.oauth import get_user_info, is_admin_email, oauth
from src.database.models import UserRole
from src.repositories.user_repository import UserRepository


class AuthService:
    """
    Service layer for Authentication business logic.
    """

    def __init__(self, db: AsyncSession):
        self.user_repo = UserRepository(db)

    async def handle_google_callback(self, request: Request) -> str:
        """
        Handle the full Google OAuth callback flow.
        
        Returns:
            str: The frontend redirect URL with JWT token.
        """
        try:
            # 1. Exchange code for token
            try:
                token = await oauth.google.authorize_access_token(request)
            except Exception as token_error:
                if "Name or service not known" in str(token_error):
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="Cannot reach Google OAuth servers.",
                    ) from token_error
                raise

            # 2. Get User Info
            user_info = await get_user_info(token)
            if not user_info:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to get user info from Google",
                )

            email = user_info.get("email")
            if not email:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email not provided by Google",
                )

            name = user_info.get("name", email.split("@")[0])
            avatar_url = user_info.get("picture")

            # 3. Check / Create / Update User
            user = await self.user_repo.get_by_email(email)

            if user:
                await self.user_repo.update(user, name=name, avatar_url=avatar_url)
            else:
                role = UserRole.ADMIN if is_admin_email(email) else UserRole.USER
                user = await self.user_repo.create(
                    email=email, name=name, avatar_url=avatar_url, role=role
                )

            # 4. Generate JWT
            jwt_token = create_access_token(
                user_id=user.id, role=user.role.value, email=user.email
            )

            # 5. Construct Redirect URL
            frontend_url = "http://localhost:8501"
            return f"{frontend_url}?token={jwt_token}"

        except HTTPException:
            raise
        except Exception as e:
            # Let the endpoint handle the logging/traceback to keep service clean of HTTP specifics?
            # Or handle logging here. Choosing to re-raise basic exceptions for now.
            raise Exception(f"Authentication failed: {str(e)}") from e
