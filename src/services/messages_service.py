from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exception import MessageServiceError, NotFoundError
from src.database.models import (
    FeedbackType,
    Message,
    MessageRole,
    Metric,
)


class MessageService:
    """
    Service layer for chat message management.
    
    Handles CRUD operations for messages including creation, retrieval,
    feedback management, and performance tracking.
    """

    def __init__(self, db: AsyncSession):
        """
        Initialize the MessageService with a database session.

        Args:
            db: The asynchronous database session for all operations.
        """
        self.db = db

    async def create_message(
        self, conversation_id: str, role: MessageRole, content: str
    ) -> Message:
        """
        Create a new message in a specific conversation.

        Args:
            conversation_id: Unique identifier for the conversation.
            role: Message role (USER or ASSISTANT).
            content: The actual text content of the message.

        Returns:
            The created Message object.

        Raises:
            MessageServiceError: If message creation fails.
        """
        try:
            logger.info(f"Creating {role} message for conversation {conversation_id}")
            message = Message(conversation_id=conversation_id, role=role, content=content)

            self.db.add(message)
            await self.db.commit()
            await self.db.refresh(message)
            return message
        except Exception as e:
            logger.error(f"Error creating message: {e}")
            await self.db.rollback()
            raise MessageServiceError("Failed to create message record.") from e

    async def get_conversation_messages(
        self, conversation_id: str, limit: int | None = None
    ) -> list[Message]:
        """
        Retrieve all messages from a specific conversation.

        Args:
            conversation_id: Unique identifier for the conversation.
            limit: Optional maximum number of messages to retrieve.

        Returns:
            List of Message objects, sorted by creation time (oldest first).

        Raises:
            MessageServiceError: If message retrieval fails.
        """
        try:
            logger.info(f"Retrieving messages for conversation {conversation_id}")
            query = (
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at.asc())
            )

            if limit:
                query = query.limit(limit)

            result = await self.db.execute(query)
            messages = result.scalars().all()
            return list(messages)
        except Exception as e:
            logger.error(
                f"Error retrieving messages for conversation {conversation_id}: {e}"
            )
            raise MessageServiceError("Failed to retrieve conversation history.") from e

    async def add_feedback_to_message(
        self, message_id: str, feedback_type: FeedbackType, feedback_comment: str | None
    ) -> Message:
        """
        Add user feedback and optional comments to an existing assistant message.

        Args:
            message_id: Unique identifier for the target message.
            feedback_type: Type of feedback (POSITIVE or NEGATIVE).
            feedback_comment: Optional detailed text feedback from the user.

        Returns:
            The updated Message object with feedback applied.

        Raises:
            NotFoundError: If the message ID does not exist.
            MessageServiceError: If the update operation fails.
        """
        message = await self.get_message_by_id(message_id)

        if not message:
            raise NotFoundError(f"Message {message_id} not found.")

        try:
            message.feedback = feedback_type
            message.feedback_comment = feedback_comment

            await self.db.commit()
            await self.db.refresh(message)
            return message
        except Exception as e:
            logger.error(f"Error adding feedback to message {message_id}: {e}")
            await self.db.rollback()
            raise MessageServiceError("Failed to save message feedback.") from e

    async def create_metric(
        self,
        message_id: str,
        llm_latency_ms: float | None,
        embedding_latency_ms: float | None,
        vector_query_latency_ms: float | None,
        total_latency_ms: float,
    ) -> Metric:
        """
        Log performance metrics for a specific message response.

        Args:
            message_id: ID of the message to track.
            llm_latency_ms: Latency for the LLM response in milliseconds.
            embedding_latency_ms: Latency for embedding generation.
            vector_query_latency_ms: Latency for vector database retrieval.
            total_latency_ms: Total end-to-end request latency.

        Returns:
            The created Metric object.

        Raises:
            MessageServiceError: If metric creation fails.
        """
        try:
            metric = Metric(
                message_id=message_id,
                llm_latency_ms=llm_latency_ms,
                embedding_latency_ms=embedding_latency_ms,
                vector_query_latency_ms=vector_query_latency_ms,
                total_latency_ms=total_latency_ms,
            )

            self.db.add(metric)
            await self.db.commit()
            await self.db.refresh(metric)
            return metric
        except Exception as e:
            logger.error(f"Error creating metric for message {message_id}: {e}")
            await self.db.rollback()
            raise MessageServiceError("Failed to log message metrics.") from e

    async def get_message_by_id(self, message_id: str) -> Message | None:
        """
        Retrieve a specific message by its unique ID.

        Args:
            message_id: Unique identifier for the message.

        Returns:
            The Message object if found, otherwise None.

        Raises:
            MessageServiceError: If fetch operation fails.
        """
        try:
            result = await self.db.execute(select(Message).where(Message.id == message_id))
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error fetching message {message_id}: {e}")
            raise MessageServiceError(f"Failed to fetch message {message_id}.") from e

    async def count_messages_in_conversation(self, conversation_id: str) -> int:
        """
        Get the total count of messages within a specific conversation.

        Args:
            conversation_id: Unique identifier for the conversation.

        Returns:
            Total number of messages as an integer.

        Raises:
            MessageServiceError: If the count operation fails.
        """
        try:
            query = select(func.count(Message.id)).where(
                Message.conversation_id == conversation_id
            )
            result = await self.db.execute(query)
            return result.scalar() or 0
        except Exception as e:
            logger.error(
                f"Error counting messages for conversation {conversation_id}: {e}"
            )
            raise MessageServiceError("Failed to count conversation messages.") from e
