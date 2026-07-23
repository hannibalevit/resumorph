from functools import lru_cache

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4.1-mini", alias="OPENAI_MODEL")
    allowed_origins: str = Field(default="http://localhost:5173", alias="ALLOWED_ORIGINS")
    openai_timeout_seconds: float = Field(default=60.0, alias="OPENAI_TIMEOUT_SECONDS")
    database_url: str = Field(default="sqlite:///./resumorph.db", alias="DATABASE_URL")
    master_encryption_key: str = Field(default="", alias="MASTER_ENCRYPTION_KEY")
    default_llm_provider: str = Field(default="openai", alias="DEFAULT_LLM_PROVIDER")
    default_openai_model: str = Field(default="gpt-4.1-mini", alias="DEFAULT_OPENAI_MODEL")
    default_gemini_model: str = Field(default="gemini-2.5-flash-lite", alias="DEFAULT_GEMINI_MODEL")
    default_claude_model: str = Field(
        default="claude-haiku-4-5-20251001", alias="DEFAULT_CLAUDE_MODEL"
    )

    model_config = SettingsConfigDict(extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
