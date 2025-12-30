from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.session import get_db
from src.services.conversation_service import ConversationService
from src.services.messages_service import MessageService


async def get_conversation_service(
    db: AsyncSession = Depends(get_db),
) -> ConversationService:
    """
    Dependency to get ConversationService instance with active db session.
    """
    return ConversationService(db)


async def get_message_service(
    db: AsyncSession = Depends(get_db),
) -> MessageService:
    """
    Dependency to get MessageService instance with active db session.
    """
    return MessageService(db)
