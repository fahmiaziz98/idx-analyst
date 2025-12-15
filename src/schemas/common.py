from datetime import datetime

from pydantic import BaseModel, Field


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
