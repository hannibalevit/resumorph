from functools import lru_cache

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()

# Single default for Ollama base URL (Field + resolve fallback when env is blank/whitespace).
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"


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
    default_ollama_model: str = Field(default="llama3.2", alias="DEFAULT_OLLAMA_MODEL")
    ollama_base_url: str = Field(default=DEFAULT_OLLAMA_BASE_URL, alias="OLLAMA_BASE_URL")
    # Generation (CPU + cold model load) can take minutes; keep this long.
    ollama_timeout_seconds: float = Field(default=300.0, alias="OLLAMA_TIMEOUT_SECONDS")
    # Reachability checks (list_models / test_connection) should fail fast when
    # the host is unreachable (e.g. Ollama still on 127.0.0.1 under Docker).
    ollama_connect_timeout_seconds: float = Field(
        default=10.0, alias="OLLAMA_CONNECT_TIMEOUT_SECONDS"
    )
    # Resume/cover-letter prompts are ~5–7k+ tokens before generation; Ollama
    # truncates silently when the window is too small. 32768 leaves room for
    # prompt + num_predict (e.g. build_resume's max_tokens=4800). Lower only if
    # your model/hardware cannot load that context.
    ollama_num_ctx: int = Field(default=32768, alias="OLLAMA_NUM_CTX")

    model_config = SettingsConfigDict(extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
