from fastapi import HTTPException
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core import settings

# Create the asynchronous database engine
engine = create_async_engine(
    url=settings.DATABASE_URL,
    echo=False,  # set false in production
    pool_size=20,  # adjust based on your needs
    max_overflow=40,  # adjust based on your needs
    pool_pre_ping=True,  # to check if connections are alive
    pool_timeout=60,
    pool_recycle=3600,
)

# sessionmaker factory for creating new AsyncSession instances
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)

async def get_db() -> AsyncSession:
    """
    Dependency for getting async database session.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Database session error: {e}")
            await session.rollback()
            raise
        finally:
            await session.close()


async def create_tables():
    """
    Initialize the database by creating all tables.
    """
    from src.database.base import Base

    async with engine.begin() as conn:
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)


async def drop_tables():
    """
    Drop all tables in the database.
    """
    from src.database.base import Base

    async with engine.begin() as conn:
        # Drop all tables
        await conn.run_sync(Base.metadata.drop_all)
