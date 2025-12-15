from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt

from src.core.config import settings
from src.database.models import UserRole


class TokenData:
    """
    Data structure for decode token
    """

    def __init__(self, user_id: str, role: str, email: str):
        self.user_id = user_id
        self.role = role
        self.email = email

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN.value

    def __repr__(self) -> str:
        return f"TokenData(user_id={self.user_id}, role={self.role}, email={self.email})"


def create_access_token(
    user_id: str,
    role: str,
    email: str,
    expires_delta: timedelta | None = None,
) -> str:
    """
    Create JWT access token

    This token will be issued after the user successfully logs in via OAuth.
    The client will store this token (localStorage/cookie) and
    send it in every request (Authorization header).

    Args:
        user_id (str): User ID
        role (str): User role
        email (str): User email
        expires_delta (Optional[timedelta], optional): Expiration time. Defaults to None.

    Returns:
        str: JWT access token
    """
    now = datetime.now(UTC)

    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(seconds=settings.jwt_expiration_seconds)

    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "exp": expire,
        "iat": now,
    }

    token = jwt.encode(
        payload,
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )

    return token


def verify_token(token: str) -> TokenData:
    """
    Verify & decode JWT access token
    This function is used in auth middleware to validate tokens
    sent by clients in the Authorization header.

    Validation checks:
    - Signature valid (token has not been modified)
    - Not expired
    - Has required fields

    Args:
        token (str): JWT access token

    Returns:
        TokenData: Token data
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )

        user_id = payload.get("sub")
        role = payload.get("role")
        email = payload.get("email")

        if user_id is None or role is None or email is None:
            raise JWTError("Invalid token")

        return TokenData(user_id, role, email)
    except JWTError:
        return None


def get_token_expiration(token: str) -> datetime | None:
    """
    Get expiration time dari token.

    Args:
        token: JWT token string

    Returns:
        Expiration datetime or None

    """
    payload = decode_token(token)
    if payload and "exp" in payload:
        return datetime.fromtimestamp(payload["exp"], tz=UTC)
    return None


def is_token_expired(token: str) -> bool:
    """
    Check if a JWT token has expired.

    Args:
        token (str): The JWT token string.

    Returns:
        bool: True if the token has expired, False otherwise.
    """
    exp_time = get_token_expiration(token)
    if exp_time:
        return datetime.now(UTC) > exp_time
    return True  # Jika tidak


def decode_token(token: str) -> dict | None:
    """Utiliy function for debugging"""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
            options={"verify_signature": False},
        )
        return payload
    except JWTError:
        return None
