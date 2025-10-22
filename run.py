"""
Run script for the API
Usage: python run.py
"""

import uvicorn

from src.core.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "src.api.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.ENVIRONMENT == "development",
        workers=1 if settings.ENVIRONMENT == "development" else settings.WORKERS,
        log_level="info",
        access_log=True,
    )
