from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.base import Base

if TYPE_CHECKING:
    from .message import Message
    from .user import User


class Conversation(Base):
    """
    Conversation model for group messages

    Every conversation:
    - Owned by a user (creator)
    - Have many messages
    - Have a title (auto-generate from first message)

    Example:
        conversation = Conversation(
            title="Project Discussion",
            user_id="qwq-uuid-1234",
        )
    """

    __tablename__ = "conversations"

    # Foregin Key User
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="ID of the user who created the conversation",
    )

    # Conversation info
    title: Mapped[str] = mapped_column(
        String(500), nullable=False, comment="Title of the conversation"
    )

    # Soft Delete
    # Using soft delete so that is not lost permanently
    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        index=True,  # Index for filter "WHERE is_deleted = False"
        comment="Whether the conversation is deleted or not",
    )

    # ===== Relationships =====
    # Many conversations belong to one user
    user: Mapped["User"] = relationship(
        "User",
        back_populates="conversations",
        lazy="joined",  # Eager load user saat query conversation
    )

    # One conversation has many messages
    messages: Mapped[list["Message"]] = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",  # Delete messages if conversation deleted
        lazy="selectin",
        order_by="Message.created_at",  # Messages sorted by timestamp
    )

    def __repr__(self) -> str:
        return f"<Conversation(id='{self.id}', title='{self.title[:30]}...')>"

    @property
    def message_count(self) -> int:
        return len(self.messages) if self.messages else 0
