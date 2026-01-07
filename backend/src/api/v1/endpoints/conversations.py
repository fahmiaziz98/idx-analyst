from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import selectinload

from src.api.dependencies import get_conversation_service, get_current_user
from src.database.models import User
from src.schemas.conversation_schema import (
    ConversationCreate,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationResponse,
    ConversationUpdate,
    MessageResponse,
)
from src.services.conversation_service import ConversationService

router = APIRouter()


@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    data: ConversationCreate,
    user: User = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service),
):
    """
    Create new conversation.
    
    Title auto-generated from first message.
    
    Example request:
    ```json
    POST /api/v1/conversations
    {
        "title": "My New Chat"
    }
    ```
    
    Example response:
    ```json
    {
        "id": "conv-123",
        "title": "My New Chat",
        "message_count": 0,
        "created_at": "2024-01-01T10:00:00",
        "updated_at": "2024-01-01T10:00:00"
    }
    ```
    """
    # TODO: Automated generate first messages using llm
    title = data.title or "New Conversation"
    
    conversation = await service.create_conversation(
        user_id=user.id,
        title=title
    )
    
    return ConversationResponse(
        id=conversation.id,
        title=conversation.title,
        message_count=0,  # New conversation, no messages yet
        created_at=conversation.created_at,
        updated_at=conversation.updated_at
    )


@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    skip: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(50, ge=1, le=100, description="Items per page"),
    user: User = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service),
):
    """
    List user's conversations.
    
    Pagination: skip + limit.
    Sorted by updated_at desc (newest first).
    
    Example request:
    ```
    GET /api/v1/conversations?skip=0&limit=20
    ```
    
    Example response:
    ```json
    {
        "items": [
            {
                "id": "conv-123",
                "title": "Chat about RAG",
                "message_count": 5,
                "created_at": "2024-01-01T10:00:00",
                "updated_at": "2024-01-01T11:00:00"
            }
        ],
        "total": 1,
        "skip": 0,
        "limit": 20
    }
    ```
    """
    conversations, message_counts, total = await service.get_user_conversations_with_count(
        user_id=user.id,
        skip=skip,
        limit=limit
    )
    
    # Build response using pre-fetched counts (O(1) lookup, no queries!)
    items = [
        ConversationResponse(
            id=conv.id,
            title=conv.title,
            message_count=message_counts.get(conv.id, 0), 
            created_at=conv.created_at,
            updated_at=conv.updated_at
        )
        for conv in conversations
    ]
    
    return ConversationListResponse(
        items=items,
        total=total,  
        skip=skip,
        limit=limit
    )


@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(
    conversation_id: str,
    user: User = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service),
):
    """
    Get conversation detail all messages.
    
    Example request:
    ```
    GET /api/v1/conversations/conv-123
    ```
    
    Example response:
    ```json
    {
        "id": "conv-123",
        "title": "Chat about RAG",
        "created_at": "2024-01-01T10:00:00",
        "updated_at": "2024-01-01T11:00:00",
        "messages": [
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
                "feedback_comment": "Helpful!",
                "created_at": "2024-01-01T10:00:05"
            }
        ]
    }
    ```
    """
    from sqlalchemy import select
    from src.database.models import Conversation
    
    query = (
        select(Conversation)
        .options(selectinload(Conversation.messages))  # Explicit eager load
        .where(
            Conversation.id == conversation_id,
            Conversation.user_id == user.id,
            Conversation.is_deleted.is_(False),
        )
    )
    
    result = await service.db.execute(query)
    conversation = result.scalar_one_or_none()
    
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found or you don't have access"
        )
    
    messages = [
        MessageResponse(
            id=msg.id,
            role=msg.role.value,
            content=msg.content,
            feedback=msg.feedback.value if msg.feedback else None,
            feedback_comment=msg.feedback_comment,
            created_at=msg.created_at
        )
        for msg in conversation.messages
    ]
    
    return ConversationDetailResponse(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=messages
    )


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: str,
    user: User = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service),
):
    """
    Delete conversation (soft delete).
    
    Example request:
    ```
    DELETE /api/v1/conversations/conv-123
    ```
    
    Response: 204 No Content (empty body)
    """
    # Delete conversation
    success = await service.delete_conversation(
        conversation_id=conversation_id,
        user_id=user.id
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found or you don't have access"
        )
    
    return None


@router.patch("/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
    conversation_id: str,
    data: ConversationUpdate,
    user: User = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service),
):
    """
    Update conversation title.
    
    Example request:
    ```json
    PATCH /api/v1/conversations/conv-123
    {
        "title": "Updated Title"
    }
    ```
    
    Example response:
    ```json
    {
        "id": "conv-123",
        "title": "Updated Title",
        "message_count": 5,
        "created_at": "2024-01-01T10:00:00",
        "updated_at": "2024-01-01T12:00:00"
    }
    ```
    """
    conversation = await service.update_conversation_title(
        conversation_id=conversation_id,
        user_id=user.id,
        new_title=data.title
    )
    
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found or you don't have access"
        )
    
    # Efficiently get message count
    from src.services.messages_service import MessageService
    message_service = MessageService(service.db)
    message_count = await message_service.count_messages_in_conversation(
        conversation_id=conversation_id
    )
    
    return ConversationResponse(
        id=conversation.id,
        title=conversation.title,
        message_count=message_count,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at
    )