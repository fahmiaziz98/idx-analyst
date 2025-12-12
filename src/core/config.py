from functools import lru_cache

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

    API_KEYS_ENCRYPTED: str | None = None
    ENCRYPTION_KEY: str | None = None
    API_KEYS: str | None = None

    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"  
    JWT_EXPIRATION_DAYS: int = 7  
    
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    OAUTH_REDIRECT_URI: str = "http://localhost:7860/auth/callback"
    
    ADMIN_EMAIL: str 
    
    HOST: str = "0.0.0.0"
    PORT: int = 7860 # | 8000
    WORKERS: int = 4
    ALLOWED_ORIGINS: str = "*"

    DATABASE_URL: str | None = None

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

    ENABLE_METRICS: bool = True
    ENABLE_HEALTH_CHECKS: bool = True
    LOG_LEVEL: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="allow",
    )

    @property
    def jwt_expiration_seconds(self) -> int:
        """JWT expiration dalam seconds."""
        return self.JWT_EXPIRATION_DAYS * 24 * 60 * 60
    

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
