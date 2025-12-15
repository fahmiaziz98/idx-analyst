import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.main import app
from src.auth.jwt import create_access_token, verify_token
from src.database.models import User, UserRole
from src.database.session import AsyncSessionLocal, create_tables, drop_tables, engine

client = TestClient(app)


@pytest_asyncio.fixture(scope="function")
async def db_session():
    """Create fresh database per test"""
    await create_tables()
    session = AsyncSessionLocal()
    try:
        yield session
    finally:
        await session.close()
        await drop_tables()
        await engine.dispose()


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession):
    """
    Create test user with proper duplicate handling.

    ✅ FIX: Check if user exists before creating
    """
    # Check if user already exists
    result = await db_session.execute(select(User).where(User.email == "test@example.com"))
    existing_user = result.scalar_one_or_none()

    if existing_user:
        return existing_user

    # Create new user
    user = User(email="test@example.com", name="Test User", role=UserRole.USER)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_admin(db_session: AsyncSession):
    """
    Create test admin with proper duplicate handling.

    ✅ FIX: Check if admin exists before creating
    """
    # Check if admin already exists
    result = await db_session.execute(select(User).where(User.email == "admin@example.com"))
    existing_admin = result.scalar_one_or_none()

    if existing_admin:
        return existing_admin

    # Create new admin
    admin = User(email="admin@example.com", name="Admin User", role=UserRole.ADMIN)
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    return admin


# ===== JWT Tests =====
def test_create_access_token():
    """Test JWT token creation"""
    token = create_access_token(user_id="user-123", email="test@example.com", role="user")

    assert isinstance(token, str)
    parts = token.split(".")
    assert len(parts) == 3


def test_verify_valid_token():
    """Test verify valid token"""
    token = create_access_token(user_id="user-123", email="test@example.com", role="user")

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
    token = create_access_token(user_id="admin-123", email="admin@example.com", role="admin")

    token_data = verify_token(token)

    assert token_data is not None
    assert token_data.is_admin is True


# ===== Auth Endpoints Tests =====
def test_auth_health():
    """Test auth health endpoint"""
    response = client.get("/api/v1/auth/health")

    assert response.status_code == 200
    data = response.json()

    assert "status" in data
    assert "oauth_configured" in data
    assert "jwt_configured" in data


def test_login_endpoint():
    """Test login endpoint (should redirect)"""
    response = client.get("/api/v1/auth/login", follow_redirects=False)

    assert response.status_code in [302, 307]
    assert "location" in response.headers
    assert "accounts.google.com" in response.headers["location"]


@pytest.mark.asyncio
async def test_get_me_without_token():
    """Test /me endpoint without token"""
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_me_with_valid_token(test_user):
    """Test /me endpoint with valid token"""
    token = create_access_token(
        user_id=test_user.id, email=test_user.email, role=test_user.role.value
    )

    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    data = response.json()

    assert data["email"] == test_user.email
    assert data["name"] == test_user.name
    assert data["role"] == test_user.role.value


@pytest.mark.asyncio
async def test_get_me_with_invalid_token():
    """Test /me endpoint with invalid token"""
    response = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer invalid_token"})

    assert response.status_code == 401


# ===== Admin Access Tests =====
@pytest.mark.asyncio
async def test_admin_check(test_user, test_admin):
    """Test admin role checking"""
    assert test_user.role == UserRole.USER
    assert test_user.is_admin is False

    assert test_admin.role == UserRole.ADMIN
    assert test_admin.is_admin is True


# ===== Integration Tests =====
def test_full_health_check():
    """Test full health check endpoint"""
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()

    assert data["api"] == "ok"
    assert "redis" in data
    assert "environment" in data


def test_root_endpoint():
    """Test root endpoint"""
    response = client.get("/")

    assert response.status_code == 200
    data = response.json()

    assert "name" in data
    assert "version" in data
    assert "docs" in data


# ===== Security Tests =====
def test_token_cannot_be_modified():
    """Test that modified token will be rejected"""
    token = create_access_token(user_id="user-123", email="test@example.com", role="user")

    modified_token = token[:-1] + "X"
    token_data = verify_token(modified_token)
    assert token_data is None


def test_expired_token_rejected():
    """Test expired token is rejected"""
    from datetime import timedelta

    token = create_access_token(
        user_id="user-123",
        email="test@example.com",
        role="user",
        expires_delta=timedelta(seconds=-1),
    )

    token_data = verify_token(token)
    assert token_data is None
