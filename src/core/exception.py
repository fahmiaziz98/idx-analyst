from datetime import datetime
from typing import Optional, Any


class ApplicationError(Exception):
    """Base class for all application-specific errors."""
    def __init__(
        self, 
        message: str, 
        code: Optional[str] = None, 
        details: Optional[Any] = None
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details


class ServiceMaintenanceError(ApplicationError):
    """
    Raised when a service is in cooldown or maintenance mode (Circuit Breaker).
    """
    def __init__(self, service_name: str, reset_time: datetime, remaining_seconds: int):
        self.service_name = service_name
        self.reset_time = reset_time
        self.remaining_seconds = remaining_seconds
        message = (
            f"Service '{service_name}' is currently in cooldown/maintenance. "
            f"Please try again in {remaining_seconds} seconds."
        )
        super().__init__(
            message=message, 
            code="SERVICE_MAINTENANCE",
            details={
                "service": service_name,
                "reset_time": reset_time.isoformat(),
                "retry_after": remaining_seconds
            }
        )


class EmbeddingServiceError(ApplicationError):
    """Raised when an error occurs in the embedding service."""
    def __init__(self, message: str, details: Optional[Any] = None):
        super().__init__(message, code="EMBEDDING_SERVICE_ERROR", details=details)


class TokenBlacklistError(ApplicationError):
    """Raised when an error occurs in the token blacklist service."""
    def __init__(self, message: str):
        super().__init__(message, code="TOKEN_BLACKLIST_ERROR")


class ConversationServiceError(ApplicationError):
    """Raised when an error occurs in the conversation service."""
    def __init__(self, message: str):
        super().__init__(message, code="CONVERSATION_SERVICE_ERROR")


class MessageServiceError(ApplicationError):
    """Raised when an error occurs in the message service."""
    def __init__(self, message: str):
        super().__init__(message, code="MESSAGE_SERVICE_ERROR")


class AuthServiceError(ApplicationError):
    """Raised when an error occurs in the authentication service."""
    def __init__(self, message: str, details: Optional[Any] = None):
        super().__init__(message, code="AUTH_SERVICE_ERROR", details=details)


class ChatServiceError(ApplicationError):
    """Raised when an error occurs in the chat service."""
    def __init__(self, message: str):
        super().__init__(message, code="CHAT_SERVICE_ERROR")


class WebSocketManagerError(ApplicationError):
    """Raised when an error occurs in the WebSocket manager."""
    def __init__(self, message: str):
        super().__init__(message, code="WEBSOCKET_MANAGER_ERROR")


class NotFoundError(ApplicationError):
    """Raised when a requested resource is not found."""
    def __init__(self, message: str):
        super().__init__(message, code="NOT_FOUND")


class DocumentProcessorError(ApplicationError):
    """Raised when an error occurs in the document processing."""
    def __init__(self, message: str):
        super().__init__(message, code="DOCUMENT_PROCESSOR_ERROR")


class ParsingError(ApplicationError):
    """Raised when an error occurs in the document parsing."""
    def __init__(self, message: str):
        super().__init__(message, code="PARSING_ERROR")


class ChunkingError(ApplicationError):
    """Raised when an error occurs in the chunking."""
    def __init__(self, message: str):
        super().__init__(message, code="CHUNKING_ERROR")


class ContextualizationError(ApplicationError):
    """Raised when an error occurs in the contextualization."""
    def __init__(self, message: str, chunk_id: Optional[str] = None, retry_count: int = 0):
        super().__init__(
            message,
            code="CONTEXTUALIZATION_ERROR",
            details={
                "chunk_id": chunk_id,
                "retry_count": retry_count
            }
        )


class ValidationError(ApplicationError):
    """Raised when a validation error occurs."""
    def __init__(self, message: str):
        super().__init__(message, code="VALIDATION_ERROR")