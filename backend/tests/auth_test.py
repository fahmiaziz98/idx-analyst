from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from fastapi import Depends, status
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from httpx import AsyncClient, ASGITransport

from src.api.main import app
from src.auth.jwt import create_access_token, verify_token
from src.auth.token_blacklist import get_token_blacklist, get_redis_connection
from src.database.models import User, UserRole
from src.database.base import Base # Base is in src.database.base
from src.database.session import get_db
from src.api.dependencies import get_current_user, get_current_user_full, StatelessUser

# Use in-memory SQLite for testing to avoid connection errors to remote host
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

client = TestClient(app)

@pytest_asyncio.fixture(scope="function")
async def db_session():
    """Create fresh database per test and mock blacklist"""
    
    # Initialize database tables
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    mock_blacklist = AsyncMock()
    mock_blacklist.is_revoked.return_value = False
    mock_blacklist.is_user_revoked.return_value = None

    # Mock Redis to avoid any real network connection
    mock_redis = AsyncMock()
    mock_redis.get.return_value = None
    mock_redis.exists.return_value = False
    
    app.dependency_overrides[get_token_blacklist] = lambda: mock_blacklist
    app.dependency_overrides[get_redis_connection] = lambda: mock_redis
    app.dependency_overrides[get_db] = override_get_db
    
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
    """Create test user with proper duplicate handling."""
    result = await db_session.execute(select(User).where(User.email == "test@example.com"))
    existing_user = result.scalar_one_or_none()

    if existing_user:
        return existing_user

    user = User(
        id="test-user-id", # Explicit ID for tests
        email="test@example.com", 
        name="Test User", 
        role=UserRole.USER
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user

@pytest_asyncio.fixture
async def test_admin(db_session: AsyncSession):
    """Create test admin with proper duplicate handling."""
    result = await db_session.execute(select(User).where(User.email == "admin@example.com"))
    existing_admin = result.scalar_one_or_none()

    if existing_admin:
        return existing_admin

    admin = User(
        id="test-admin-id",
        email="admin@example.com", 
        name="Admin User", 
        role=UserRole.ADMIN
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    return admin

# ===== JWT Tests =====
def test_create_access_token():
    """Test JWT token creation"""
    token, jti = create_access_token(user_id="user-123", email="test@example.com", role="user")

    assert isinstance(token, str)
    assert isinstance(jti, str)
    parts = token.split(".")
    assert len(parts) == 3

def test_verify_valid_token():
    """Test verify valid token"""
    token, _ = create_access_token(user_id="user-123", email="test@example.com", role="user")

    token_data = verify_token(token)

    assert token_data is not None
    assert token_data.user_id == "user-123"
    assert token_data.email == "test@example.com"
    assert token_data.role == "user"

def test_verify_invalid_token():
    """Test verify invalid token"""
    invalid_token = "invalid.token.string"
    token_data = verify_token(invalid_token)
    assert token_data is None

def test_token_with_admin_role():
    """Test token with admin role"""
    token, _ = create_access_token(user_id="admin-123", email="admin@example.com", role="admin")

    token_data = verify_token(token)

    assert token_data is not None
    assert token_data.is_admin is True

def test_login_endpoint():
    """Test login endpoint (should redirect)"""
    response = client.get("/api/v1/auth/login", follow_redirects=False)

    assert response.status_code in [302, 307]
    assert "location" in response.headers
    assert "accounts.google.com" in response.headers["location"]

@pytest.mark.asyncio
async def test_get_me_without_token(db_session):
    """Test /me endpoint without token"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/auth/me")
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_get_me_with_valid_token(db_session, test_user):
    """Test /me endpoint with valid token"""
    token, _ = create_access_token(
        user_id=test_user.id, email=test_user.email, role=test_user.role.value
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    data = response.json()

    assert data["email"] == test_user.email
    assert data["name"] == test_user.name
    assert data["role"] == test_user.role.value

@pytest.mark.asyncio
async def test_get_me_with_invalid_token(db_session):
    """Test /me endpoint with invalid token"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/auth/me", headers={"Authorization": "Bearer invalid_token"})

    assert response.status_code in [401, 403]

def test_token_cannot_be_modified():
    """Test that modified token will be rejected"""
    token_str, _ = create_access_token(user_id="user-123", email="test@example.com", role="user")

    modified_token = token_str[:-1] + "X"
    token_data = verify_token(modified_token)
    assert token_data is None

def test_expired_token_rejected():
    """Test expired token is rejected"""
    token, _ = create_access_token(
        user_id="user-123",
        email="test@example.com",
        role="user",
        expires_delta=timedelta(seconds=-1),
    )

    token_data = verify_token(token)
    assert token_data is None
