from fastapi import HTTPException, status
from loguru import logger


async def verify_content_type(content_type: str = None):
    """
    Verify content type for POST requests
    """
    if content_type and "application/json" not in content_type:
        logger.warning(f"Invalid content type: {content_type}")
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Content-Type must be application/json",
        )
    return content_type
