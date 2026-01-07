import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from jose import JWTError, jwt
from loguru import logger

from src.core.config import settings
from src.database.models import UserRole


class TokenData:
    """
    Data structure for decoded token information.

    Attributes:
        user_id: Unique user identifier
        role: User role (admin/user)
        email: User email address
        jti: JWT ID for revocation tracking
        token_type: Type of token (access/refresh)
        issued_at: Token issuance timestamp
        expires_at: Token expiration timestamp
    """

    def __init__(
        self,
        user_id: str,
        role: str,
        email: str,
        jti: str,
        token_type: Literal["access", "refresh"] = "access",
        issued_at: datetime | None = None,
        expires_at: datetime | None = None,
    ):
        self.user_id = user_id
        self.role = role
        self.email = email
        self.jti = jti
        self.token_type = token_type
        self.issued_at = issued_at
        self.expires_at = expires_at

    @property
    def is_admin(self) -> bool:
        """Check if user has admin role"""
        return self.role == UserRole.ADMIN.value

    @property
    def is_expired(self) -> bool:
        """Check if token is expired"""
        if self.expires_at:
            return datetime.now(UTC) > self.expires_at
        return False

    @property
    def time_until_expiry(self) -> timedelta | None:
        """Get time remaining until token expires"""
        if self.expires_at:
            return self.expires_at - datetime.now(UTC)
        return None

    def __repr__(self) -> str:
        return (
            f"TokenData(user_id={self.user_id}, role={self.role}, "
            f"token_type={self.token_type}, jti={self.jti[:8]}...)"
        )


class TokenPair:
    """
    Container for access and refresh token pair.

    Attributes:
        access_token: Short-lived access token
        refresh_token: Long-lived refresh token
        access_token_jti: JTI of access token
        refresh_token_jti: JTI of refresh token
        token_type: Token type (always "bearer")
    """

    def __init__(
        self,
        access_token: str,
        refresh_token: str,
        access_token_jti: str,
        refresh_token_jti: str,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.access_token_jti = access_token_jti
        self.refresh_token_jti = refresh_token_jti
        self.token_type = "bearer"

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses"""
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "token_type": self.token_type,
        }


def create_access_token(
    user_id: str,
    role: str,
    email: str,
    expires_delta: timedelta | None = None,
) -> tuple[str, str]:
    """
    Create JWT access token with security enhancements.

    Args:
        user_id: User's unique identifier
        role: User's role (admin/user)
        email: User's email address
        expires_delta: Optional custom expiration time

    Returns:
        tuple: (token_string, jti)

    Example:
        >>> token, jti = create_access_token("user-123", "user", "user@example.com")
        >>> print(f"Token: {token[:20]}... JTI: {jti}")
    """
    now = datetime.now(UTC)

    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(seconds=settings.jwt_access_token_expire_seconds)

    jti = str(uuid.uuid4())

    # Build JWT payload with security claims
    payload = {
        "sub": user_id,  # Subject (user ID)
        "email": email,  # User email
        "role": role,  # User role
        "exp": expire,  # Expiration time
        "iat": now,  # Issued at
        "nbf": now,  # Not before
        "jti": jti,  # JWT ID for revocation
        "token_type": "access",  # Token type
        "iss": "idx-analyst-api",  # Issuer
        "aud": "idx-analyst-client",  # Audience
    }

    # Sign token
    token = jwt.encode(
        payload,
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )

    logger.info(
        f"Access token created for user {user_id} (expires in {expires_delta or settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES}m)"
    )

    return token, jti


def create_refresh_token(
    user_id: str,
    expires_delta: timedelta | None = None,
) -> tuple[str, str]:
    """
    Create JWT refresh token for obtaining new access tokens.

    Refresh tokens:
    - Have longer expiration (30 days default)
    - Use separate secret key
    - Contain minimal claims for security
    - Can be rotated on each use

    Args:
        user_id: User's unique identifier
        expires_delta: Optional custom expiration time

    Returns:
        tuple: (token_string, jti)

    Example:
        >>> refresh_token, jti = create_refresh_token("user-123")
    """
    now = datetime.now(UTC)

    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(seconds=settings.jwt_refresh_token_expire_seconds)

    jti = str(uuid.uuid4())

    # Minimal payload for refresh tokens (security best practice)
    payload = {
        "sub": user_id,
        "exp": expire,
        "iat": now,
        "nbf": now,
        "jti": jti,
        "token_type": "refresh",
        "iss": "idx-analyst-api",
        "aud": "idx-analyst-client",
    }

    # Use separate secret for refresh tokens
    token = jwt.encode(
        payload,
        settings.JWT_REFRESH_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )

    logger.info(
        f"Refresh token created for user {user_id} (expires in {settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS} days)"
    )

    return token, jti


def create_token_pair(
    user_id: str,
    role: str,
    email: str,
) -> TokenPair:
    """
    Create both access and refresh tokens.

    Args:
        user_id: User's unique identifier
        role: User's role
        email: User's email address

    Returns:
        TokenPair object containing both tokens

    Example:
        >>> tokens = create_token_pair("user-123", "user", "user@example.com")
        >>> print(tokens.to_dict())
    """
    access_token, access_jti = create_access_token(user_id, role, email)
    refresh_token, refresh_jti = create_refresh_token(user_id)

    return TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        access_token_jti=access_jti,
        refresh_token_jti=refresh_jti,
    )


def verify_token(
    token: str, token_type: Literal["access", "refresh"] = "access"
) -> TokenData | None:
    """
    Verify and decode JWT token with comprehensive validation.

    Validation checks:
    - Signature validity
    - Token not expired
    - Token not used before nbf (not before) time
    - Token type matches expected type
    - All required claims present
    - Issuer and audience match

    Args:
        token: JWT token string
        token_type: Expected token type ("access" or "refresh")

    Returns:
        TokenData object if valid, None if invalid

    Example:
        >>> token_data = verify_token(token_string, "access")
        >>> if token_data:
        ...     print(f"User: {token_data.email}")
    """
    try:
        # Select appropriate secret based on token type
        secret = settings.JWT_SECRET if token_type == "access" else settings.JWT_REFRESH_SECRET

        # Decode and verify token
        payload = jwt.decode(
            token,
            secret,
            algorithms=[settings.JWT_ALGORITHM],
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_nbf": True,
                "verify_iat": True,
                "verify_aud": True,
                "verify_iss": True,
            },
            audience="idx-analyst-client",
            issuer="idx-analyst-api",
        )

        # Verify token type matches expected
        payload_token_type = payload.get("token_type")
        if payload_token_type != token_type:
            logger.warning(f"Token type mismatch: expected {token_type}, got {payload_token_type}")
            return None

        # Extract claims
        user_id = payload.get("sub")
        jti = payload.get("jti")

        # Validate required claims
        if not user_id or not jti:
            logger.warning("Token missing required claims (sub or jti)")
            return None

        # For access tokens, verify additional claims
        if token_type == "access":
            role = payload.get("role")
            email = payload.get("email")

            if not role or not email:
                logger.warning("Access token missing role or email claim")
                return None
        else:
            # Refresh tokens have minimal claims
            role = None
            email = None

        # Extract timestamps
        issued_at = (
            datetime.fromtimestamp(payload.get("iat"), tz=UTC) if payload.get("iat") else None
        )
        expires_at = (
            datetime.fromtimestamp(payload.get("exp"), tz=UTC) if payload.get("exp") else None
        )

        return TokenData(
            user_id=user_id,
            role=role,
            email=email,
            jti=jti,
            token_type=token_type,
            issued_at=issued_at,
            expires_at=expires_at,
        )

    except JWTError as e:
        logger.warning(f"Token verification failed: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error during token verification: {e}")
        return None


def get_token_expiration(token: str) -> datetime | None:
    """
    Get expiration time from token without full verification.

    Useful for:
    - Determining TTL for token blacklist
    - Checking if token refresh is needed
    - Logging and monitoring

    Args:
        token: JWT token string

    Returns:
        Expiration datetime or None if invalid

    Example:
        >>> expiry = get_token_expiration(token)
        >>> print(f"Token expires at: {expiry}")
    """
    try:
        # Decode without verification (just for inspection)
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
            options={"verify_signature": False, "verify_exp": False},
        )

        exp_timestamp = payload.get("exp")
        if exp_timestamp:
            return datetime.fromtimestamp(exp_timestamp, tz=UTC)
        return None

    except JWTError:
        return None


def get_token_remaining_seconds(token: str) -> int | None:
    """
    Calculate remaining seconds until token expiration.

    Useful for setting Redis TTL for token blacklist.

    Args:
        token: JWT token string

    Returns:
        Seconds until expiration, or None if invalid

    Example:
        >>> seconds = get_token_remaining_seconds(token)
        >>> await blacklist.revoke_token(token, expiry_seconds=seconds)
    """
    expiry = get_token_expiration(token)
    if expiry:
        remaining = (expiry - datetime.now(UTC)).total_seconds()
        return max(0, int(remaining))  # Never return negative
    return None


def is_token_expired(token: str) -> bool:
    """
    Check if token is expired without full verification.

    Args:
        token: JWT token string

    Returns:
        True if expired, False otherwise
    """
    expiry = get_token_expiration(token)
    if expiry:
        return datetime.now(UTC) > expiry
    return True  # Treat invalid tokens as expired
