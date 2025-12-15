from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import User, UserRole


class UserRepository:
    """
    Repository for User data access.
    Abstracts direct DB interactions.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_email(self, email: str) -> User | None:
        """Get user by email address."""
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def create(
        self,
        email: str,
        name: str,
        avatar_url: str | None,
        role: UserRole = UserRole.USER,
    ) -> User:
        """Create a new user."""
        user = User(
            email=email,
            name=name,
            avatar_url=avatar_url,
            role=role,
            last_login=datetime.now(UTC),
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def update(self, user: User, name: str | None = None, avatar_url: str | None = None) -> User:
        """Update existing user."""
        if name:
            user.name = name
        if avatar_url:
            user.avatar_url = avatar_url
        
        user.last_login = datetime.now(UTC)
        await self.db.commit()
        await self.db.refresh(user)
        return user
