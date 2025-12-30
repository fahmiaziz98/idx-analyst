from fastapi import APIRouter, Depends, HTTPException, status

from src.api.dependencies import get_conversation_service, get_message_service
from src.auth.dependency import get_current_user
from src.database.models import User
from src.schemas.conversation_schema import FeedbackCreate, MessageListResponse, MessageResponse
from src.services.conversation_service import ConversationService
from src.services.messages_service import MessageService

# Router
router = APIRouter()


@router.get("/conversations/{conversation_id}/messages", response_model=MessageListResponse)
async def get_messages(
    conversation_id: str,
    user: User = Depends(get_current_user),
    c_service: ConversationService = Depends(get_conversation_service),
    m_service: MessageService = Depends(get_message_service),
):
    """
    Get messages from conversation.
    
    Security: Verify user owns conversation.
    
    Example request:
    ```
    GET /api/v1/conversations/conv-123/messages
    ```
    
    Example response:
    ```json
    {
        "items": [
            {
                "id": "msg-1",
                "role": "user",
                "content": "What is RAG?",
                "feedback": null,
                "created_at": "2024-01-01T10:00:00"
            },
            {
                "id": "msg-2",
                "role": "assistant",
                "content": "RAG stands for...",
                "feedback": "positive",
                "created_at": "2024-01-01T10:00:05"
            }
        ],
        "total": 2,
        "conversation_id": "conv-123"
    }
    ```
    """
    conversation = await c_service.get_conversation_by_id(
        conversation_id=conversation_id,
        user_id=user.id
    )
    
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found or you don't have access"
        )
    
    messages = await m_service.get_conversation_messages(
        conversation_id=conversation_id,
        limit=50
    )
    
    items = [
        MessageResponse(
            id=msg.id,
            role=msg.role.value,
            content=msg.content,
            feedback=msg.feedback.value if msg.feedback else None,
            feedback_comment=msg.feedback_comment,
            created_at=msg.created_at
        )
        for msg in messages
    ]
    
    return MessageListResponse(
        items=items,
        total=len(items),
        conversation_id=conversation_id
    )


@router.post("/messages/{message_id}/feedback", response_model=MessageResponse)
async def add_feedback(
    message_id: str,
    data: FeedbackCreate,
    user: User = Depends(get_current_user),
    c_service: ConversationService = Depends(get_conversation_service),
    m_service: MessageService = Depends(get_message_service),
):
    """
    Add feedback ke assistant message.
    
    User bisa kasih thumbs up/down + optional comment.
    
    Security: Verify message belongs to user's conversation.
    
    Example request:
    ```json
    POST /api/v1/messages/msg-123/feedback
    {
        "feedback": "positive",
        "comment": "Very helpful explanation!"
    }
    ```
    
    Example response:
    ```json
    {
        "id": "msg-123",
        "role": "assistant",
        "content": "RAG stands for...",
        "feedback": "positive",
        "feedback_comment": "Very helpful explanation!",
        "created_at": "2024-01-01T10:00:00"
    }
    ```
    """
    # Get message
    message = await m_service.get_message_by_id(message_id)
    
    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found"
        )
    
    # Verify ownership (message.conversation.user_id == user.id)
    conversation = await c_service.get_conversation_by_id(
        conversation_id=message.conversation_id,
        user_id=user.id
    )
    
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this message"
        )
    
    # Add feedback
    updated_message = await m_service.add_feedback_to_message(
        message_id=message_id,
        feedback_type=data.feedback,
        feedback_comment=data.comment
    )
    
    return MessageResponse(
        id=updated_message.id,
        role=updated_message.role.value,
        content=updated_message.content,
        feedback=updated_message.feedback.value if updated_message.feedback else None,
        feedback_comment=updated_message.feedback_comment,
        created_at=updated_message.created_at
    )