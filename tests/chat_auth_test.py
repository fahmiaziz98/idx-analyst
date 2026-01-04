import pytest
import pytest_asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

from fastapi import Depends, status
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from src.api.main import app
from src.api.dependencies import get_current_user, get_current_user_full, StatelessUser
from src.auth.jwt import create_access_token
from src.auth.token_blacklist import get_token_blacklist, get_redis_connection
from src.core import settings
from src.database.base import Base
from src.database.models import User, UserRole, Conversation, Message, MessageRole
from src.database.session import get_db

# Disable CSRF for testing
settings.ENABLE_CRF_PROTECTION = False

# --- Test Infrastructure (In-Memory SQLite) ---
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(
    TEST_DATABASE_URL, 
    echo=False,
    connect_args={"check_same_thread": False}
)
TestSessionLocal = async_sessionmaker(
    bind=test_engine,
    expire_on_commit=False,
    class_=AsyncSession,
    autoflush=False,
)

async def override_get_db() -> AsyncSession:
    async with TestSessionLocal() as session:
        yield session

@pytest_asyncio.fixture(scope="function")
async def db_session():
    """Create fresh database per test and mock external services"""
    # Initialize database tables
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Mock Blacklist & Redis
    mock_blacklist = AsyncMock()
    mock_blacklist.is_revoked.return_value = False
    mock_blacklist.is_user_revoked.return_value = None

    mock_redis = AsyncMock()
    mock_redis.get.return_value = None
    mock_redis.exists.return_value = False
    
    # Apply Overrides
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_token_blacklist] = lambda: mock_blacklist
    app.dependency_overrides[get_redis_connection] = lambda: mock_redis
    
    # Mock full user lookup to avoid issues with stateless reconstructed user
    async def mock_get_current_user_full(db: AsyncSession = Depends(get_db), sc_user: StatelessUser = Depends(get_current_user)):
        result = await db.execute(select(User).where(User.id == sc_user.id))
        return result.scalar_one_or_none()
    app.dependency_overrides[get_current_user_full] = mock_get_current_user_full

    async with TestSessionLocal() as session:
        yield session
    
    # Clean up
    app.dependency_overrides.clear()
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession):
    """Create a persistent test user in the in-memory DB"""
    user = User(
        id="test-user-uuid",
        email="chat-test@example.com",
        name="Chat Tester",
        role=UserRole.USER
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user

@pytest_asyncio.fixture
async def auth_headers(test_user):
    """Generate auth headers for the test user"""
    token, _ = create_access_token(
        user_id=test_user.id,
        email=test_user.email,
        role=test_user.role.value
    )
    return {"Authorization": f"Bearer {token}"}

# --- Tests ---

@pytest.mark.asyncio
async def test_full_chat_flow(db_session, test_user, auth_headers):
    """
    Test the integrated flow:
    1. Create conversation
    2. Add messages
    3. List conversations (check message count)
    4. Get conversation detail
    """
    # Create a client with CSRF cookies to avoid DeprecationWarning
    csrf_token = "test-csrf-token"
    cookies = {"csrf_token": csrf_token}
    
    async with AsyncClient(
        transport=ASGITransport(app=app), 
        base_url="http://test",
        cookies=cookies
    ) as ac:
        
        # 1. Create Conversation
        conv_payload = {"title": "Test RAG Chat"}
        headers = {**auth_headers, "X-CSRF-Token": csrf_token}
        
        response = await ac.post(
            "/api/v1/conversations", 
            json=conv_payload, 
            headers=headers
        )
        assert response.status_code == 201
        conv_data = response.json()
        conv_id = conv_data["id"]
        assert conv_data["title"] == "Test RAG Chat"
        assert conv_data["message_count"] == 0

        # 2. Manually add messages (Simulating what chat service/websocket would do)
        # We'll add 1 user message and 1 assistant message
        msg1 = Message(conversation_id=conv_id, role=MessageRole.USER, content="Hello Bot")
        msg2 = Message(conversation_id=conv_id, role=MessageRole.ASSISTANT, content="Hello Human, I am RAG bot")
        db_session.add_all([msg1, msg2])
        await db_session.commit()

        # 3. List Conversations (Verify Message Count Optimization)
        # This calls ConversationService.get_user_conversations_with_count
        list_response = await ac.get("/api/v1/conversations", headers=auth_headers)
        assert list_response.status_code == 200
        list_data = list_response.json()
        assert list_data["total"] >= 1
        
        # Find our conversation
        target_conv = next((c for c in list_data["items"] if c["id"] == conv_id), None)
        assert target_conv is not None
        assert target_conv["message_count"] == 2 # 🚀 Optimization verify: count should be 2

        # 4. Get Conversation Detail (Check Messages)
        detail_response = await ac.get(f"/api/v1/conversations/{conv_id}", headers=auth_headers)
        assert detail_response.status_code == 200
        detail_data = detail_response.json()
        assert detail_data["id"] == conv_id
        assert len(detail_data["messages"]) == 2
        assert detail_data["messages"][0]["role"] == "user"
        assert detail_data["messages"][1]["role"] == "assistant"

@pytest.mark.asyncio
async def test_get_messages_endpoint(db_session, test_user, auth_headers):
    """Test specifically the /messages endpoint"""
    # Create conv and messages
    conv = Conversation(user_id=test_user.id, title="Message Test")
    db_session.add(conv)
    await db_session.commit()
    await db_session.refresh(conv)

    msg = Message(conversation_id=conv.id, role=MessageRole.USER, content="Direct message check")
    db_session.add(msg)
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get(f"/api/v1/conversations/{conv.id}/messages", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["content"] == "Direct message check"

@pytest.mark.asyncio
async def test_access_denied_other_user_conv(db_session, test_user, auth_headers):
    """Security: Ensure user cannot access other user's conversations"""
    # Create conversation for a different user
    other_user = User(id="other-uuid", email="other@example.com", name="Other", role=UserRole.USER)
    db_session.add(other_user)
    await db_session.commit()
    
    other_conv = Conversation(user_id=other_user.id, title="Private Chat")
    db_session.add(other_conv)
    await db_session.commit()
    await db_session.refresh(other_conv)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Try to get detail of other user's conversation
        response = await ac.get(f"/api/v1/conversations/{other_conv.id}", headers=auth_headers)
        assert response.status_code == 404 # Should be 404 or 403 based on implementation
        
        # Try to get messages of other user's conversation
        msg_response = await ac.get(f"/api/v1/conversations/{other_conv.id}/messages", headers=auth_headers)
        assert msg_response.status_code == 404
