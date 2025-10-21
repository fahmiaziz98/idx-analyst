from fastapi import Depends, HTTPException, status
from core.security import validate_api_key
from loguru import logger


async def get_current_api_key(api_key: str = Depends(validate_api_key)) -> str:
    """
    Dependency to get and validate current API key
    """
    return api_key


async def verify_content_type(content_type: str = None):
    """
    Verify content type for POST requests
    """
    if content_type and "application/json" not in content_type:
        logger.warning(f"Invalid content type: {content_type}")
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Content-Type must be application/json"
        )
    return content_type