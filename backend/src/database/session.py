from fastapi import HTTPException
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
import asyncio
from typing import AsyncGenerator

from src.core import settings

MAX_RETRIES = 3
RETRY_DELAY = 2  

engine = create_async_engine(
    url=settings.DATABASE_URL,
    echo=False,
    pool_size=19, 
    max_overflow=29,  
    pool_pre_ping=True,  
    pool_recycle=1800,  
    pool_timeout=30,  
    connect_args={
        "timeout": 30,
        "command_timeout": 30,
        "server_settings": {
            "application_name": "your_app_name",
            "jit": "off"
        },
        "ssl": "require"
    },
)


AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
    autoflush=False,  
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for getting async database session with retry logic.
    """
    retries = 0
    last_error = None
    
    while retries < MAX_RETRIES:
        try:
            async with AsyncSessionLocal() as session:
                # Test connection
                from sqlalchemy import text
                await session.execute(text("SELECT 1"))
                yield session
                await session.commit()
                return
        except HTTPException:
            raise
        except Exception as e:
            last_error = e
            retries += 1
            logger.warning(
                f"Database connection attempt {retries}/{MAX_RETRIES} failed: {e}"
            )
            
            if retries < MAX_RETRIES:
                await asyncio.sleep(RETRY_DELAY * retries)  # exponential backoff
            else:
                logger.error(f"Database session error after {MAX_RETRIES} retries: {e}")
                raise HTTPException(
                    status_code=503,
                    detail="Database connection unavailable. Please try again later."
                )


async def create_tables():
    """
    Initialize the database by creating all tables with retry logic.
    """
    from src.database.base import Base
    
    retries = 0
    while retries < MAX_RETRIES:
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables created successfully")
            return
        except Exception as e:
            retries += 1
            logger.warning(
                f"Create tables attempt {retries}/{MAX_RETRIES} failed: {e}"
            )
            if retries < MAX_RETRIES:
                await asyncio.sleep(RETRY_DELAY * retries)
            else:
                logger.error(f"Failed to create tables after {MAX_RETRIES} retries")
                raise


async def drop_tables():
    """
    Drop all tables in the database.
    """
    from src.database.base import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    logger.info("Database tables dropped")
