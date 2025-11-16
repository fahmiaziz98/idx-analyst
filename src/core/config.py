from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Application configuration settings
    """

    # API Configuration
    API_TITLE: str = "RAG Chatbot API"
    API_VERSION: str = "1.0.0"
    API_DESCRIPTION: str = "Scalable RAG Chatbot with LangGraph"
    ENVIRONMENT: str = "development"

    # Security
    API_KEYS: str
    ALLOWED_ORIGINS: str = "*"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 7860
    WORKERS: int = 4

    # Rate Limiting
    RATE_LIMIT_REQUESTS: int
    RATE_LIMIT_WINDOW: int

    # llm model
    MODEL_GPT_OSS_20B: str = "groq:openai/gpt-oss-20b"
    MODEL_GEMINI_FLASH: str = "google_genai:gemini-2.0-flash"

    # vector name
    DATA_PATH: str = "data/COMBINED_DATA.json"
    TOTAL_DOCUMENTS: int = 0

    # cross-encoder model
    COHERE_API_KEY: str

    # Api embedding
    EMBEDDING_API_URL: str
    # Instruction
    INSTRUCTION_DOC: str = "This is a passage from the annual financial report of an Indonesian public company"
    INSTRUCTION_QUERY: str = "Given a financial analysis or QA query, retrieve relevant passages from annual reports of Indonesian public companies"
   

    # Setting Qdrant DB
    QDRANT_API_KEY: str
    QDRANT_BASE_URL: str
    COLLECTION: str = "document"

    # Tavily Tool
    TAVILY_API_KEY: str

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "allow"

    @property
    def api_keys_list(self) -> list[str]:
        """Parse comma-separated API keys"""
        return [key.strip() for key in self.API_KEYS.split(",")]

    @property
    def allowed_origins_list(self) -> list[str]:
        """Parse comma-separated origins"""
        if self.ALLOWED_ORIGINS == "*":
            return ["*"]
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",")]


@lru_cache
def get_settings() -> Settings:
    """Cache settings instance"""
    return Settings()


settings = get_settings()
