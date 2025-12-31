from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exception import ConversationServiceError, NotFoundError
from src.database.models import Conversation


class ConversationService:
    """
    Service layer for conversation management.
    """

    def __init__(self, db: AsyncSession):
        """
        Initialize the ConversationService with a database session.

        Args:
            db: The asynchronous database session for all operations.
        """
        self.db = db

    async def create_conversation(self, user_id: str, title: str) -> Conversation:
        """
        Create a new conversation for a specific user.

        Args:
            user_id: The ID of the user creating the conversation.
            title: The title of the conversation.

        Returns:
            The created Conversation object.

        Raises:
            ConversationServiceError: If the conversation creation fails.

        Example:
            conversation = await create_conversation(
                user_id="user-123",
                title="How to implement RAG?",
            )
        """
        try:
            logger.info(f"Creating conversation for user: {user_id}")
            conversation = Conversation(
                user_id=user_id,
                title=title,
            )
            self.db.add(conversation)
            await self.db.commit()
            await self.db.refresh(conversation)
            return conversation

        except Exception as e:
            logger.error(f"Error creating conversation: {e}")
            raise ConversationServiceError("Failed to create conversation record.") from e


    async def get_user_conversations(
        self, user_id: str, skip: int = 0, limit: int = 15, include_deleted: bool = False
    ) -> list[Conversation]:
        """
        Retrieve a list of conversations for a specific user with pagination support.

        Args:
            user_id: The ID of the user whose conversations are being retrieved.
            skip: The number of conversations to skip (offset).
            limit: The maximum number of conversations to return.
            include_deleted: Whether to include soft-deleted conversations.

        Returns:
            A list of Conversation objects.

        Raises:
            ConversationServiceError: If the retrieval process fails.

        Example:
            conversations = await get_user_conversations(
                user_id="user-123",
                db=db,
                limit=10
            )
        """
        try:
            logger.info(f"Retrieving conversations for user: {user_id}")
            query = select(Conversation).where(Conversation.user_id == user_id)

            if not include_deleted:
                query = query.where(Conversation.is_deleted.is_(False))

            # Sort by updated_at (newest first)
            query = query.order_by(Conversation.updated_at.desc())

            # Pagination
            query = query.offset(skip).limit(limit)

            result = await self.db.execute(query)
            conversations = result.scalars().all()

            return list(conversations)

        except Exception as e:
            logger.error(f"Error retrieving user conversations: {e}")
            raise ConversationServiceError("Failed to retrieve user conversations.") from e

    async def get_user_conversations_with_count(
        self, user_id: str, skip: int = 0, limit: int = 15
    ) -> tuple[list[Conversation], dict[str, int], int]:
        """
        Retrieve conversations with message counts and total count efficiently.

        Args:
            user_id: The ID of the user whose conversations are being retrieved.
            skip: The number of conversations to skip (offset).
            limit: The maximum number of conversations to return.
        
        Returns:
            Tuple of (conversations, message_counts_dict, total_count):
            - conversations: List of Conversation objects
            - message_counts_dict: Dict mapping conversation_id to message count
            - total_count: Total number of conversations (for pagination)
        
        Example:
            convs, counts, total = await service.get_user_conversations_with_count(
                user_id="user-123", skip=0, limit=20
            )
            # Uses only 2-3 queries instead of 20+ queries!
        """
        try:
            from sqlalchemy import func
            from src.database.models import Message
            
            logger.info(f"Retrieving conversations with counts for user: {user_id}")
            
            # Query 1: Get total count
            count_query = select(func.count(Conversation.id)).where(
                Conversation.user_id == user_id,
                Conversation.is_deleted.is_(False)
            )
            total_result = await self.db.execute(count_query)
            total_count = total_result.scalar() or 0
            
            # Query 2: Get conversations (paginated)
            query = (
                select(Conversation)
                .where(
                    Conversation.user_id == user_id,
                    Conversation.is_deleted.is_(False)
                )
                .order_by(Conversation.updated_at.desc())
                .offset(skip)
                .limit(limit)
            )
            
            result = await self.db.execute(query)
            conversations = list(result.scalars().all())
            
            if not conversations:
                return ([], {}, 0)
            
            # Query 3: Get message counts for all conversations in ONE query
            conversation_ids = [conv.id for conv in conversations]
            message_count_query = (
                select(
                    Message.conversation_id,
                    func.count(Message.id).label("count")
                )
                .where(Message.conversation_id.in_(conversation_ids))
                .group_by(Message.conversation_id)
            )
            
            count_result = await self.db.execute(message_count_query)
            message_counts = {row[0]: row[1] for row in count_result.all()}
            
            logger.info(
                f"Retrieved {len(conversations)} conversations with counts "
                f"(total: {total_count}) using 3 efficient queries"
            )
            
            return (conversations, message_counts, total_count)
            
        except Exception as e:
            logger.error(f"Error retrieving conversations with counts: {e}")
            raise ConversationServiceError(
                "Failed to retrieve conversations with message counts."
            ) from e



    async def get_conversation_by_id(
        self, conversation_id: str, user_id: str
    ) -> Conversation | None:
        """
        Get a specific conversation by its ID and verify user ownership.

        Args:
            conversation_id: The unique identifier of the conversation.
            user_id: The ID of the user to verify ownership.

        Returns:
            The Conversation object if found and authorized, otherwise None.

        Raises:
            ConversationServiceError: If the database operation fails.
        """
        try:
            result = await self.db.execute(
                select(Conversation).where(
                    Conversation.id == conversation_id,
                    Conversation.user_id == user_id,
                    Conversation.is_deleted.is_(False),
                )
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error fetching conversation {conversation_id}: {e}")
            raise ConversationServiceError(f"Failed to fetch conversation {conversation_id}.") from e


    async def delete_conversation(self, conversation_id: str, user_id: str) -> bool:
        """
        Perform a soft delete on a conversation.

        Soft deleting sets the 'is_deleted' flag to True without removing the record
        from the database, allowing for potential restoration and valid historical analytics.

        Args:
            conversation_id: The ID of the conversation to delete.
            user_id: The ID of the user to verify ownership.

        Returns:
            True if the deletion was successful.

        Raises:
            NotFoundError: If the conversation is not found or user is not authorized.
            ConversationServiceError: If the commit fails.
        """
        conversation = await self.get_conversation_by_id(conversation_id, user_id)

        if not conversation:
            raise NotFoundError(f"Conversation {conversation_id} not found or access denied.")

        try:
            conversation.is_deleted = True
            await self.db.commit()
            return True
        except Exception as e:
            logger.error(f"Error deleting conversation {conversation_id}: {e}")
            await self.db.rollback()
            raise ConversationServiceError("Failed to delete the conversation.") from e


    async def update_conversation_title(
        self, conversation_id: str, user_id: str, new_title: str,
    ) -> Conversation:
        """
        Update the title of an existing conversation.

        Args:
            conversation_id: The ID of the conversation to update.
            user_id: The ID of the user to verify ownership.
            new_title: The new title for the conversation.

        Returns:
            The updated Conversation object.

        Raises:
            NotFoundError: If the conversation is not found or user is not authorized.
            ConversationServiceError: If the update fails.
        """
        conversation = await self.get_conversation_by_id(conversation_id, user_id)

        if not conversation:
            raise NotFoundError(f"Conversation {conversation_id} not found or access denied.")

        try:
            conversation.title = new_title
            await self.db.commit()
            await self.db.refresh(conversation)
            return conversation
        except Exception as e:
            logger.error(f"Error updating title for conversation {conversation_id}: {e}")
            await self.db.rollback()
            raise ConversationServiceError("Failed to update the conversation title.") from e

    @staticmethod
    def generate_title_from_message(message: str, max_length: int = 50) -> str:
        """
        Generate a conversation title based on the content of the first message.

        Rules:
        - Truncate at max_length (default 50 characters).
        - Trim trailing/leading whitespace.
        - Append "..." if the message was truncated.

        Args:
            message: The original user message content.
            max_length: Maximum allowed length for the title.

        Returns:
            A formatted string to be used as a title.
        """
        title = message.strip()

        if len(title) > max_length:
            title = title[:max_length].strip() + "..."

        return title
