from datetime import datetime

from pydantic import BaseModel


class APIKeyMetadata(BaseModel):
    """Metadata for API key tracking."""

    key_hash: str
    created_at: datetime
    last_used: datetime | None = None
    is_active: bool = True
