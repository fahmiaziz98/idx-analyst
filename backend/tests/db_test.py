import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import selectinload, sessionmaker

from src.database.base import Base
from src.database.models import (
    Conversation,
    FeedbackType,
    Message,
    MessageRole,
    Metric,
    User,
    UserRole,
)

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def db_session():
    """
    Fixture untuk create fresh database per test.

    Flow:
    1. Create all tables
    2. Yield session untuk test
    3. Drop all tables (cleanup)
    """
    # Override engine untuk testing
    test_engine = create_async_engine(
        TEST_DATABASE_URL, echo=False, connect_args={"check_same_thread": False}
    )

    # Create tables
    async with test_engine.begin() as conn:
        await conn.execute(text("PRAGMA foreign_keys=ON"))  # Enable FK for SQLite
        await conn.run_sync(Base.metadata.create_all)

    # Create session
    async_session = sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)

    async with async_session() as session:
        yield session

    # Drop tables
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await test_engine.dispose()


@pytest.mark.asyncio
async def test_create_user(db_session: AsyncSession):
    """Test create user."""
    # Create user
    user = User(email="test@example.com", name="Test User", role=UserRole.USER)

    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    # Assertions
    assert user.id is not None
    assert user.email == "test@example.com"
    assert user.role == UserRole.USER
    assert user.created_at is not None

    # Query user dari database
    result = await db_session.execute(select(User).where(User.email == "test@example.com"))
    queried_user = result.scalar_one_or_none()

    assert queried_user is not None
    assert queried_user.email == user.email


@pytest.mark.asyncio
async def test_create_conversation(db_session: AsyncSession):
    """Test create conversation dengan relationship."""
    # Create user first
    user = User(email="test@example.com", name="Test User")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    # Create conversation
    conversation = Conversation(user_id=user.id, title="Test Conversation")
    db_session.add(conversation)
    await db_session.commit()
    await db_session.refresh(conversation)

    # Assertions
    assert conversation.id is not None
    assert conversation.user_id == user.id
    assert conversation.title == "Test Conversation"
    assert conversation.is_deleted is False

    # Test relationship
    assert conversation.user.email == "test@example.com"


@pytest.mark.asyncio
async def test_create_message(db_session: AsyncSession):
    """Test create message dengan feedback."""
    # Create user & conversation
    user = User(email="test@example.com", name="Test User")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    conversation = Conversation(user_id=user.id, title="Test")
    db_session.add(conversation)
    await db_session.commit()
    await db_session.refresh(conversation)

    # Create user message
    user_msg = Message(
        conversation_id=conversation.id, role=MessageRole.USER, content="What is RAG?"
    )

    # Create assistant message dengan feedback
    assistant_msg = Message(
        conversation_id=conversation.id,
        role=MessageRole.ASSISTANT,
        content="RAG stands for Retrieval Augmented Generation...",
        feedback=FeedbackType.POSITIVE,
        feedback_comment="Very helpful!",
    )

    db_session.add_all([user_msg, assistant_msg])
    await db_session.commit()

    # Assertions
    assert user_msg.role == MessageRole.USER
    assert assistant_msg.role == MessageRole.ASSISTANT
    assert assistant_msg.has_feedback is True
    assert assistant_msg.is_positive_feedback is True


@pytest.mark.asyncio
async def test_create_metric(db_session: AsyncSession):
    """Test create metric."""
    # Create full chain: user -> conversation -> message -> metric
    user = User(email="test@example.com", name="Test User")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    conversation = Conversation(user_id=user.id, title="Test")
    db_session.add(conversation)
    await db_session.commit()
    await db_session.refresh(conversation)

    message = Message(
        conversation_id=conversation.id, role=MessageRole.ASSISTANT, content="Response"
    )
    db_session.add(message)
    await db_session.commit()
    await db_session.refresh(message)

    # Create metric
    metric = Metric(
        message_id=message.id,
        llm_latency_ms=850.5,
        embedding_latency_ms=120.3,
        vector_query_latency_ms=45.2,
        total_latency_ms=1015.0,
    )
    db_session.add(metric)
    await db_session.commit()
    await db_session.refresh(metric)

    # Assertions
    assert metric.llm_latency_ms == 850.5
    assert metric.total_latency_ms == 1015.0
    assert metric.is_slow is False  # < 3000ms

    # Test relationship
    assert metric.message.content == "Response"


@pytest.mark.asyncio
async def test_user_conversations_relationship(db_session: AsyncSession):
    """Test one-to-many relationship (user -> conversations)."""
    # 1. Create user
    user = User(email="test@example.com", name="Test User")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    # 2. Create conversations linked to user
    conv1 = Conversation(user_id=user.id, title="Conversation 1")
    conv2 = Conversation(user_id=user.id, title="Conversation 2")
    db_session.add_all([conv1, conv2])
    await db_session.commit()
    await db_session.refresh(user, attribute_names=["conversations"])

    result = await db_session.execute(
        select(User).where(User.id == user.id).options(selectinload(User.conversations))
    )

    queried_user = result.unique().scalar_one()

    assert len(queried_user.conversations) == 2
    titles = sorted([c.title for c in queried_user.conversations])
    assert titles == ["Conversation 1", "Conversation 2"]


@pytest.mark.asyncio
async def test_soft_delete(db_session: AsyncSession):
    """Test soft delete conversation."""
    # Create user & conversation
    user = User(email="test@example.com", name="Test User")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    conversation = Conversation(user_id=user.id, title="Test")
    db_session.add(conversation)
    await db_session.commit()
    await db_session.refresh(conversation)

    # Soft delete
    conversation.is_deleted = True
    await db_session.commit()

    # Query non-deleted conversations
    result = await db_session.execute(
        select(Conversation).where(
            Conversation.user_id == user.id,
            Conversation.is_deleted == False,  # noqa: E712
        )
    )
    active_conversations = result.scalars().all()

    # Assertions
    assert len(active_conversations) == 0  # No active conversations

    # Query semua conversations (including deleted)
    result = await db_session.execute(select(Conversation).where(Conversation.user_id == user.id))
    all_conversations = result.scalars().all()

    assert len(all_conversations) == 1  # Still exists in DB
    assert all_conversations[0].is_deleted is True
