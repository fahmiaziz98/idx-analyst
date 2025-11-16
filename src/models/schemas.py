from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Chat request schema."""

    messages: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="The input messages for the chat model.",
    )
    conversation_id: str | None = Field(
        None,
        description="Optional conversation ID to maintain context across messages.",
    )
    metadata: dict[str, Any] | None = Field(
        default_factory=dict,
        description="Optional metadata for additional context.",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "messages": "what is Rag?",
                "conversation_id": "conv-123",
                "metadata": {"user_id": "user-456", "timestamp": "2025-10-21T10:30:00"},
            }
        }


class ChatResponse(BaseModel):
    """Chat response schema"""

    response: str = Field(..., description="AI response")
    conversation_id: str | None = Field(None, description="Conversation ID")
    metadata: dict[str, Any] | None = Field(default_factory=dict, description="Additional metadata")

    class Config:
        json_schema_extra = {
            "example": {
                "response": "RAG adalah Retrieval-Augmented Generation...",
                "conversation_id": "conv-123",
                "metadata": {"tokens": 150, "timestamp": "2025-10-21T10:30:00"},
            }
        }


class StreamChunk(BaseModel):
    """Streaming chunk schema"""

    content: str = Field(..., description="Chunk content")
    done: bool = Field(default=False, description="Is streaming done")
    metadata: dict[str, Any] | None = Field(default_factory=dict, description="Chunk metadata")


class WebSocketMessage(BaseModel):
    """WebSocket message schema"""

    type: str = Field(..., description="Message type: 'message', 'error', 'info'")
    content: str = Field(..., description="Message content")
    conversation_id: str | None = None
    metadata: dict[str, Any] | None = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.now)


class ErrorResponse(BaseModel):
    """Error response schema"""

    error: str = Field(..., description="Error message")
    detail: str | None = Field(None, description="Detailed error information")
    timestamp: datetime = Field(default_factory=datetime.now)

    class Config:
        json_schema_extra = {
            "example": {
                "error": "Invalid request",
                "detail": "Message field is required",
                "timestamp": "2025-10-21T10:30:00",
            }
        }


class HealthResponse(BaseModel):
    """Health check response"""

    status: str = Field(default="healthy")
    version: str
    timestamp: datetime = Field(default_factory=datetime.now)
