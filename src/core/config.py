from functools import lru_cache
from typing import Optional

from loguru import logger
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application configuration.
    """

    API_TITLE: str = "IDX-Analyst RAG API"
    API_VERSION: str = "1.0.0"
    API_DESCRIPTION: str = "MVP RAG system for Indonesian financial reports"
    ENVIRONMENT: str = Field(default="development", pattern="^(development|staging|production)$")

    API_KEYS_ENCRYPTED: Optional[str] = None
    ENCRYPTION_KEY: Optional[str] = None
    API_KEYS: Optional[str] = None

    HOST: str = "0.0.0.0"
    PORT: int = Field(default=7860, ge=1024, le=65535)
    WORKERS: int = Field(default=4, ge=1, le=32)
    ALLOWED_ORIGINS: str = "*"

    RATE_LIMIT_REQUESTS: int = Field(default=100, ge=1, le=10000)
    RATE_LIMIT_WINDOW: int = Field(default=60, ge=1, le=3600)

    MODEL_GPT_OSS_20B: str = "groq:openai/gpt-oss-20b"
    MODEL_GEMINI_FLASH: str = "google_genai:gemini-2.0-flash"

    DATA_PATH: str = "data/COMBINED_DATA.json"
    TOTAL_DOCUMENTS: int = 0

    COHERE_API_KEY: Optional[str] = None
    TAVILY_API_KEY: Optional[str] = None
    LLAMA_PARSE_KEY: Optional[str] = None

    EMBEDDING_API_URL: str 
    INSTRUCTION_DOC: str = (
        "This is a passage from the annual financial report "
        "of an Indonesian public company"
    )
    INSTRUCTION_QUERY: str = (
        "Given a financial analysis or QA query, retrieve relevant passages "
        "from annual reports of Indonesian public companies"
    )

    QDRANT_API_KEY: Optional[str] = None
    QDRANT_BASE_URL: str
    COLLECTION: str = "document"

    CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = Field(default=5, ge=1, le=20)
    CIRCUIT_BREAKER_SUCCESS_THRESHOLD: int = Field(default=2, ge=1, le=10)
    CIRCUIT_BREAKER_TIMEOUT: int = Field(default=60, ge=10, le=600)

    MAX_RESPONSE_SIZE: int = Field(default=50_000, ge=1_000, le=500_000)
    MAX_BUFFER_ITEMS: int = Field(default=1_000, ge=100, le=10_000)
    MEMORY_WARNING_THRESHOLD_MB: int = Field(default=500, ge=100, le=2000)
    MEMORY_CRITICAL_THRESHOLD_MB: int = Field(default=1000, ge=200, le=4000)

    ENABLE_METRICS: bool = True
    ENABLE_HEALTH_CHECKS: bool = True
    LOG_LEVEL: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="allow",
    )

    # ==================== Validators ====================
    @field_validator("ENVIRONMENT")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Ensure environment is valid."""
        valid_envs = ["development", "staging", "production"]
        if v not in valid_envs:
            raise ValueError(f"ENVIRONMENT must be one of {valid_envs}")
        return v

    @field_validator("EMBEDDING_API_URL", "QDRANT_BASE_URL")
    @classmethod
    def validate_urls(cls, v: str) -> str:
        """Ensure URLs are properly formatted."""
        if not v.startswith(("http://", "https://")):
            raise ValueError(f"URL must start with http://, or https://: {v}")
        return v.rstrip("/")  # Remove trailing slash

    @model_validator(mode="after")
    def validate_api_keys(self):
        """Ensure at least one API key source is provided."""
        if not self.API_KEYS_ENCRYPTED and not self.API_KEYS:
            logger.warning(
                "⚠️  No API keys configured! Set API_KEYS_ENCRYPTED or API_KEYS "
                "in environment variables."
            )
        return self

    @model_validator(mode="after")
    def validate_production_settings(self):
        """Ensure production environment has secure settings."""
        if self.ENVIRONMENT == "production":
            if self.API_KEYS and not self.API_KEYS_ENCRYPTED:
                logger.warning(
                    "⚠️  PRODUCTION WARNING: Using plain API_KEYS. "
                    "Switch to API_KEYS_ENCRYPTED for better security!"
                )

            if self.ALLOWED_ORIGINS == "*":
                logger.warning(
                    "⚠️  PRODUCTION WARNING: ALLOWED_ORIGINS is set to '*'. "
                    "Restrict to specific domains for security!"
                )

        return self

    # ==================== Properties ====================
    @property
    def api_keys_list(self) -> list[str]:
        """
        Get decrypted API keys list.

        Returns:
            List of API keys (decrypted if encrypted)
        """
        # Try encrypted keys first
        if self.API_KEYS_ENCRYPTED and self.ENCRYPTION_KEY:
            try:
                from src.core.security import api_key_manager

                return api_key_manager.decrypt_api_keys(self.API_KEYS_ENCRYPTED)
            except Exception as e:
                logger.error(f"Failed to decrypt API keys: {e}")
                # Fallback to plain keys
                pass

        # Fallback to plain keys
        if self.API_KEYS:
            return [key.strip() for key in self.API_KEYS.split(",") if key.strip()]

        logger.warning("No API keys available!")
        return []

    @property
    def allowed_origins_list(self) -> list[str]:
        """Parse comma-separated CORS origins."""
        if self.ALLOWED_ORIGINS == "*":
            return ["*"]
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        """Check if running in production."""
        return self.ENVIRONMENT == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development."""
        return self.ENVIRONMENT == "development"

    # ==================== Methods ====================
    def get_circuit_breaker_config(self) -> dict:
        """Get circuit breaker configuration."""
        return {
            "failure_threshold": self.CIRCUIT_BREAKER_FAILURE_THRESHOLD,
            "success_threshold": self.CIRCUIT_BREAKER_SUCCESS_THRESHOLD,
            "timeout": self.CIRCUIT_BREAKER_TIMEOUT,
        }

    def get_memory_config(self) -> dict:
        """Get memory management configuration."""
        return {
            "max_response_size": self.MAX_RESPONSE_SIZE,
            "max_buffer_items": self.MAX_BUFFER_ITEMS,
            "warning_threshold_mb": self.MEMORY_WARNING_THRESHOLD_MB,
            "critical_threshold_mb": self.MEMORY_CRITICAL_THRESHOLD_MB,
        }

    def log_configuration(self):
        """Log important configuration (without sensitive data)."""
        logger.info("=" * 60)
        logger.info("Application Configuration")
        logger.info("=" * 60)
        logger.info(f"Environment: {self.ENVIRONMENT}")
        logger.info(f"API Version: {self.API_VERSION}")
        logger.info(f"Host: {self.HOST}:{self.PORT}")
        logger.info(f"Workers: {self.WORKERS}")
        logger.info(f"Rate Limit: {self.RATE_LIMIT_REQUESTS} req/{self.RATE_LIMIT_WINDOW}s")
        logger.info(f"Qdrant: {self.QDRANT_BASE_URL}")
        logger.info(f"Embedding API: {self.EMBEDDING_API_URL}")
        logger.info(f"Collection: {self.COLLECTION}")
        logger.info(f"Max Response Size: {self.MAX_RESPONSE_SIZE:,} chars")
        logger.info(f"Circuit Breaker: Enabled (threshold={self.CIRCUIT_BREAKER_FAILURE_THRESHOLD})")
        logger.info(f"Metrics: {'Enabled' if self.ENABLE_METRICS else 'Disabled'}")
        logger.info(f"API Keys: {len(self.api_keys_list)} configured")
        logger.info("=" * 60)


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.

    Returns:
        Settings singleton instance
    """
    settings_instance = Settings()

    if settings_instance.is_development:
        settings_instance.log_configuration()

    return settings_instance


# Global settings instance
settings = get_settings()