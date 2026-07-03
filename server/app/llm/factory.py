from app.llm.base import LlmProvider
from app.llm.claude_provider import ClaudeProvider
from app.llm.gemini_provider import GeminiProvider
from app.llm.openai_provider import OpenAiProvider


def get_llm_provider(provider: str) -> LlmProvider:
    if provider == "openai":
        return OpenAiProvider()
    if provider == "gemini":
        return GeminiProvider()
    if provider == "claude":
        return ClaudeProvider()
    raise ValueError(f"Unsupported LLM provider: {provider}")
