from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from src.database.models import FeedbackType, MessageRole


class ConversationCreate(BaseModel):
    """
    Schema for create conversation.
    
    Optional: title can be auto-generated from first message.
    """
    title: Optional[str] = Field(
        None,
        description="Conversation title (auto-generated if not provided)",
        max_length=500
    )


class ConversationUpdate(BaseModel):
    """Schema for update conversation."""
    title: str = Field(
        ...,
        description="New conversation title",
        min_length=1,
        max_length=500
    )


class MessageResponse(BaseModel):
    """
    Schema for message response.
    
    Used to serialize message object to JSON.
    """
    id: str
    role: str  # "user" or "assistant"
    content: str
    feedback: Optional[str] = None  # "positive" or "negative"
    feedback_comment: Optional[str] = None
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class ConversationResponse(BaseModel):
    """
    Schema for conversation response.
    
    Include conversation info + message count.
    """
    id: str
    title: str
    message_count: int = 0  # Total messages dalam conversation
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class ConversationDetailResponse(BaseModel):
    """
    Schema for conversation detail (with messages).
    
    Used for GET /conversations/{id} that returns
    conversation info + all messages.
    """
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    messages: List[MessageResponse] = []
    
    model_config = ConfigDict(from_attributes=True)


class FeedbackCreate(BaseModel):
    """
    Schema for add feedback to message.
    
    User can give thumbs up/down + optional comment.
    """
    feedback: FeedbackType = Field(..., description="Feedback type (positive/negative)")
    comment: Optional[str] = Field(
        None,
        description="Optional comment (why positive/negative)",
        max_length=1000
    )


# class PaginationParams(BaseModel):
#     """
#     Schema for pagination parameters.
    
#     Standard pagination: skip + limit.
#     """
#     skip: int = Field(0, ge=0, description="Number of items to skip")
#     limit: int = Field(15, ge=1, le=100, description="Number of items to return")


class ConversationListResponse(BaseModel):
    """
    Schema for list conversations response.
    
    Include pagination info + items.
    """
    items: List[ConversationResponse]
    total: int = Field(..., description="Total conversations (for pagination)")
    skip: int
    limit: int


class MessageListResponse(BaseModel):
    """
    Schema for list messages response.
    """
    items: List[MessageResponse]
    total: int
    conversation_id: str