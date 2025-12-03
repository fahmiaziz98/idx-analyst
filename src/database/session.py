from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core import settings

# Create the asynchronous database engine
engine = create_async_engine(
    url=settings.DATABASE_URL,
    echo=True,  # set false in production
    pool_size=5,  # adjust based on your needs
    max_overflow=10,  # adjust based on your needs
    pool_pre_ping=True,  # to check if connections are alive
)

# sessionmaker factory for creating new AsyncSession instances
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency that provides an asynchronous database session.
    Yields:
        AsyncSession: An asynchronous database session.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
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
