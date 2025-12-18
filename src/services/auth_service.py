# src/services/auth_service.py - Fix return type and logic

from fastapi import HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.oauth import get_user_info, is_admin_email, oauth
from src.database.models import User, UserRole
from src.repositories.user_repository import UserRepository


class AuthService:
    """Service layer for Authentication business logic."""

    def __init__(self, db: AsyncSession):
        self.user_repo = UserRepository(db)

    async def handle_google_callback(self, request: Request) -> User:  # Changed return type
        """
        Handle the full Google OAuth callback flow.
        
        Returns:
            User: The authenticated user object
        """
        try:
            # 1. Exchange code for token
            token = await oauth.google.authorize_access_token(request)

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
                user = await self.user_repo.update(user, name=name, avatar_url=avatar_url)
            else:
                role = UserRole.ADMIN if is_admin_email(email) else UserRole.USER
                user = await self.user_repo.create(
                    email=email, name=name, avatar_url=avatar_url, role=role
                )

            return user  

        except HTTPException:
            raise
        except Exception as e:
            raise Exception(f"Authentication failed: {str(e)}") from e
