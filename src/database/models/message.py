from enum import Enum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.base import Base

if TYPE_CHECKING:
    from src.database.models.conversation import Conversation
    from src.database.models.metric import Metric


class MessageRole(str, Enum):
    """
    Role for messages

    - USER: message from user
    - ASSISTANT: response from LLM
    """

    USER = "user"
    ASSISTANT = "assistant"


class FeedbackType(str, Enum):
    """
    Feedback type for assistant messages

    - POSITIVE: thumbs up
    - NEGATIVE: thumbs down
    """

    POSITIVE = "positive"
    NEGATIVE = "negative"


class Message(Base):
    """
    Message model for chat messages

    Each message:
    - Part of a conversation
    - Has a role (user/assistant)
    - Can have feedback (only for assistant messages)

    Example:
        # User message
        user_msg = Message(
            conversation_id="conv-123",
            role=MessageRole.USER,
            content="What is RAG?"
        )

        # Assistant message
        assistant_msg = Message(
            conversation_id="conv-123",
            role=MessageRole.ASSISTANT,
            content="RAG stands for...",
            feedback=FeedbackType.POSITIVE
        )
    """

    __tablename__ = "messages"

    # Foreign Key
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,  # Index from query "all messages from conversation X"
        comment="ID of the conversation this message belongs to",
    )

    # Message Content
    role: Mapped[MessageRole] = mapped_column(
        nullable=False,
        index=True,  # Index for filter by role
        comment="Role: user or assistant",
    )

    content: Mapped[str] = mapped_column(Text, nullable=False, comment="Content of the message")

    # Feedback System
    # Only applicable for assistant messages
    feedback: Mapped[FeedbackType | None] = mapped_column(
        nullable=True, index=True, comment="User feedback: positive or negative"
    )

    feedback_comment: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Optional comment from user about the feedback"
    )

    # Relationships
    # Many messages belong to one conversation
    conversation: Mapped["Conversation"] = relationship(
        "Conversation", back_populates="messages", lazy="joined"
    )

    # One message has one metric (optional)
    # uselist=False: one-to-one relationship
    metric: Mapped[Optional["Metric"]] = relationship(
        "Metric",
        back_populates="message",
        uselist=False,  # One-to-one (satu message max satu metric)
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        """Pretty print to debugging."""
        content_preview = self.content[:50] + "..." if len(self.content) > 50 else self.content
        return f"<Message(role='{self.role.value}', content='{content_preview}')>"

    @property
    def has_feedback(self) -> bool:
        """Helper property to check if message has feedback."""
        return self.feedback is not None

    @property
    def is_positive_feedback(self) -> bool:
        """Helper property for check positive feedback."""
        return self.feedback == FeedbackType.POSITIVE
