import secrets
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Security-focused settings with validation and environment-aware defaults.

    CRITICAL: All secrets must be at least 32 characters and cryptographically secure.
    """

    API_TITLE: str = "IDX-Analyst RAG API"
    API_VERSION: str = "1.1.0"
    API_DESCRIPTION: str = "MVP RAG system for Indonesian financial reports"
    ENVIRONMENT: Literal["development", "staging", "production"] = Field(
        default="development", description="Application environment"
    )

    # JWT Settings
    JWT_SECRET: str = Field(
        ..., min_length=32, description="Secret key for JWT token signing (min 32 chars)"
    )
    JWT_REFRESH_SECRET: str = Field(
        ..., min_length=32, description="Separate secret for refresh tokens (min 32 chars)"
    )
    JWT_ALGORITHM: str = Field(default="HS256")
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=15)  # Short-lived access tokens
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=30)

    # Session Settings
    SESSION_SECRET: str = Field(
        ..., min_length=32, description="Secret key for session middleware (min 32 chars)"
    )
    SESSION_MAX_AGE: int = Field(default=86400)  # 24 hours

    # CSRF Protection
    CSRF_SECRET: str = Field(
        ..., min_length=32, description="Secret key for CSRF tokens (min 32 chars)"
    )

    # OAuth Settings
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    OAUTH_STATE_EXPIRE_MINUTES: int = Field(default=10)

    # Email Settings
    ADMIN_EMAIL: str

    # Server Settings
    HOST: str = "0.0.0.0"
    PORT: int = 7860  # | 8000
    WORKERS: int = 4
    
    # Database Settings
    DATABASE_URL: str | None = None

    # Cookie Settings
    COOKIE_DOMAIN: str | None = Field(default=None, description="Cookie domain for token storage")
    COOKIE_SECURE: bool | None = Field(
        default=None, description="Require HTTPS for cookies (auto-set based on environment)"
    )
    COOKIE_SAMESITE: Literal["lax", "strict", "none"] = Field(default="lax")

    # Redis Settings (for token blacklist)
    REDIS_TOKEN: str | None = None
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0", description="Redis URL for token blacklist and caching"
    )
    REDIS_MAX_CONNECTIONS: int = Field(default=50)

    # Allowed Redirect Domains
    ALLOWED_REDIRECT_DOMAINS: list[str] = Field(
        default_factory=lambda: ["localhost", "127.0.0.1"],
        description="Whitelist of allowed redirect domains for OAuth",
    )
    ALLOWED_ORIGINS: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:8501", 
            "http://localhost:3000", 
            "http://127.0.0.1:8501",
            "http://127.0.0.1:3000",
            "http://localhost:5173",
            "http://127.0.0.1:5173"
        ],
        description="Whitelist of allowed origins for CORS",
    )

    # Frontend URL
    FRONTEND_URL: str = Field(
        default="http://localhost:8501", description="Frontend application URL"
    )

    # Security Headers
    ENABLE_SECURITY_HEADERS: bool = Field(default=True)
    ENABLE_CRF_PROTECTION: bool = True
    HSTS_MAX_AGE: int = Field(default=31536000)  # 1 year

    MODEL_GPT_OSS_20B: str = "groq:openai/gpt-oss-20b"
    MODEL_GEMINI_FLASH: str = "google_genai:gemini-2.5-flash-lite"

    DATA_PATH: str = "data/COMBINED_DATA.json"
    TOTAL_DOCUMENTS: int = 0

    COHERE_API_KEY: str | None = None
    TAVILY_API_KEY: str | None = None
    LLAMA_PARSE_KEY: str | None = None

    EMBEDDING_API_URL: str
    INSTRUCTION_DOC: str = (
        "This is a passage from the annual financial report of an Indonesian public company"
    )
    INSTRUCTION_QUERY: str = (
        "Given a financial analysis or QA query, retrieve relevant passages "
        "from annual reports of Indonesian public companies"
    )

    QDRANT_API_KEY: str | None = None
    QDRANT_BASE_URL: str
    COLLECTION: str = "document"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="allow",
    )

    @field_validator("JWT_SECRET", "JWT_REFRESH_SECRET", "SESSION_SECRET", "CSRF_SECRET")
    @classmethod
    def validate_secret_strength(cls, v: str, info) -> str:
        """Validate that secrets are strong and not default values"""
        field_name = info.field_name

        # Check minimum length
        if len(v) < 32:
            raise ValueError(f"{field_name} must be at least 32 characters long")

        # Check for weak/default values
        weak_secrets = [
            "changeme",
            "secret",
            "default",
            "password",
            "12345678901234567890123456789012",  # Sequential numbers
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",  # Repeated characters
        ]

        if v.lower() in weak_secrets:
            raise ValueError(
                f"{field_name} cannot be a weak or default value. "
                f"Generate a secure secret using: python -c 'import secrets; print(secrets.token_urlsafe(64))'"
            )

        # Warn if entropy seems low (all same character repeated)
        if len(set(v)) < 8:
            raise ValueError(
                f"{field_name} appears to have low entropy (too many repeated characters)"
            )

        return v

    @model_validator(mode="after")
    def validate_unique_secrets(self) -> "Settings":
        """Ensure all secrets are unique"""
        secrets_map = {
            "JWT_SECRET": self.JWT_SECRET,
            "JWT_REFRESH_SECRET": self.JWT_REFRESH_SECRET,
            "SESSION_SECRET": self.SESSION_SECRET,
            "CSRF_SECRET": self.CSRF_SECRET,
        }

        # Check for duplicate secrets
        seen = {}
        for name, value in secrets_map.items():
            if value in seen.values():
                raise ValueError(
                    f"{name} must be different from other secrets. "
                    "Each security component requires a unique secret key."
                )
            seen[name] = value

        return self

    @model_validator(mode="after")
    def set_environment_defaults(self) -> "Settings":
        """Set secure defaults based on environment"""
        if self.ENVIRONMENT == "production":
            # Force secure settings in production
            if self.COOKIE_SECURE is None:
                self.COOKIE_SECURE = True

            if not self.FRONTEND_URL.startswith("https://"):
                raise ValueError("FRONTEND_URL must use HTTPS in production environment")

            if (
                "localhost" in self.ALLOWED_REDIRECT_DOMAINS
                or "127.0.0.1" in self.ALLOWED_REDIRECT_DOMAINS
            ):
                raise ValueError(
                    "localhost/127.0.0.1 cannot be in ALLOWED_REDIRECT_DOMAINS in production"
                )
        else:
            # Development defaults
            if self.COOKIE_SECURE is None:
                self.COOKIE_SECURE = False

        return self

    @property
    def is_production(self) -> bool:
        """Check if running in production"""
        return self.ENVIRONMENT == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development"""
        return self.ENVIRONMENT == "development"

    @property
    def jwt_access_token_expire_seconds(self) -> int:
        """Get JWT access token expiration in seconds"""
        return self.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60

    @property
    def jwt_refresh_token_expire_seconds(self) -> int:
        """Get JWT refresh token expiration in seconds"""
        return self.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60

    @staticmethod
    def generate_secret(length: int = 64) -> str:
        """
        Generate a cryptographically secure secret key.

        Args:
            length: Length of the secret (default: 64)

        Returns:
            URL-safe base64-encoded secret string

        Example:
            >>> Settings.generate_secret()
            'xvJm2kL...'  # 64+ character secure string
        """
        return secrets.token_urlsafe(length)


@lru_cache
def get_security_settings() -> Settings:
    """
    Get cached security settings instance.

    Returns:
        SecuritySettings singleton instance
    """
    return Settings()


# Export for convenience
settings = get_security_settings()
