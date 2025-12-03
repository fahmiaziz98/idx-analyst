from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.base import Base

if TYPE_CHECKING:
    from .conversation import Conversation


class UserRole(str, Enum):
    """
    Benefits of using Enum for user roles:
    1. Type Safety: Enums provide a way to define a set of named values, ensuring that only valid roles are used throughout the codebase.
    2. Database constraints: When using Enums with SQLAlchemy, the database can enforce that only valid enum values are stored in the corresponding column.
    3. Auto-completion and Readability: Enums improve code readability and provide better auto-completion support in IDEs, making it easier for developers to work with user roles.
    """

    ADMIN = "admin"
    USER = "user"


class User(Base):
    """
    User model for authentication and authorization.

    Relationships:
        - posts: One-to-many relationship with Post model.

    Example:
        user = User(
            username="johndoe",
            email="johndoe@gmail.com,
            role=UserRole.USER
        )
    """

    __tablename__ = "users"

    # basic info (Oauth)
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
        comment="Email from OAuth2 provider",
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Display name from Oauth",
    )

    avatar_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Avatar URL from Oauth",
    )

    # Role and Permissions
    role: Mapped[UserRole] = mapped_column(
        default=UserRole.USER,
        nullable=False,
        comment="User role",
    )

    # Activity tracking
    last_login: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last login timestamp",
    )

    # ===== Relationships =====
    # One user has many conversations
    # back_populates: two-way relationship (User <-> Conversation)
    # cascade: if a user is deleted, delete their conversations too (Optional)
    conversations: Mapped[list["Conversation"]] = relationship(
        "Conversation",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email} role={self.role}>"

    @property
    def is_admin(self) -> bool:
        """
        Check if the user has admin role.
        Returns:
            bool: True if user is admin, False otherwise.
        """
        return self.role == UserRole.ADMIN
