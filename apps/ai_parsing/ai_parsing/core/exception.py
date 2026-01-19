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
