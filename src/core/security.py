from fastapi import HTTPException, Security, status
from fastapi.security.api_key import APIKeyHeader
from loguru import logger

from .config import settings

api_key_header = APIKeyHeader(name="X-API-KEY", auto_error=False)


async def validate_api_key(api_key: str = Security(api_key_header)) -> str:
    """
    Validate API key from header

    Args:
        api_key: API key from X-API-Key header

    Returns:
        str: Validated API key

    Raises:
        HTTPException: If API key is invalid or missing
    """
    if not api_key:
        logger.warning("Missing API key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Please provide a valid API key.",
            headers={"WWW-Authenticate": "API Key"},
        )

    if api_key not in settings.api_keys_list:
        logger.warning(f"Invalid API key attempt: {api_key[:8]}...")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key. Access forbidden.",
            headers={"WWW-Authenticate": "API Key"},
        )
    return api_key
