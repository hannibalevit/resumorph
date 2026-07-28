"""Ollama LLM provider — local/unauthenticated HTTP API via httpx.

Uses native ``/api/tags`` and ``/api/chat`` (not the OpenAI-compat ``/v1`` layer)
so structured output can pass a JSON schema through ``format``. Context window
defaults are raised via ``num_ctx`` because Ollama's stock window silently
truncates long resume+job prompts.
"""

from typing import Any

import httpx

from app.config import get_settings
from app.llm.base import LlmProvider, parse_json_response

DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"


class OllamaProvider(LlmProvider):
    provider_name = "ollama"

    def __init__(self, base_url: str | None = None) -> None:
        settings = get_settings()
        resolved = (base_url or settings.ollama_base_url or DEFAULT_OLLAMA_BASE_URL).rstrip("/")
        self.base_url = resolved
        self._timeout = settings.ollama_timeout_seconds
        self._num_ctx = settings.ollama_num_ctx

    def _headers(self, api_key: str) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        # Local Ollama needs no auth; a non-empty key is only for LAN proxies /
        # future optional tokens (stored encrypted like other providers).
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url, timeout=self._timeout, headers={"Accept": "application/json"}
        )

    async def list_models(self, api_key: str) -> list[str]:
        async with self._client() as client:
            response = await client.get("/api/tags", headers=self._headers(api_key))
            response.raise_for_status()
            payload = response.json()
        names = [
            str(item.get("name") or item.get("model") or "").strip()
            for item in payload.get("models", [])
            if isinstance(item, dict)
        ]
        return sorted({name for name in names if name})

    async def generate_text(
        self, api_key: str, model: str, system_prompt: str, user_prompt: str, max_tokens: int = 2000
    ) -> str:
        body: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {"num_ctx": self._num_ctx, "num_predict": max_tokens},
        }
        async with self._client() as client:
            response = await client.post("/api/chat", json=body, headers=self._headers(api_key))
            response.raise_for_status()
            payload = response.json()
        message = payload.get("message") or {}
        content = message.get("content") if isinstance(message, dict) else None
        return str(content or "").strip()

    async def generate_json(
        self,
        api_key: str,
        model: str,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, Any] | None = None,
        max_tokens: int = 2000,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "format": response_schema if response_schema is not None else "json",
            "options": {"num_ctx": self._num_ctx, "num_predict": max_tokens},
        }
        async with self._client() as client:
            response = await client.post("/api/chat", json=body, headers=self._headers(api_key))
            response.raise_for_status()
            payload = response.json()
        message = payload.get("message") or {}
        content = message.get("content") if isinstance(message, dict) else None
        text = str(content or "").strip()
        if not text:
            raise ValueError("Ollama returned an empty chat response.")
        return parse_json_response(text)

    async def test_connection(self, api_key: str, model: str | None = None) -> dict[str, Any]:
        models = await self.list_models(api_key)
        preview = f"reachable; {len(models)} model(s)"
        if model and model not in models and models:
            preview = f"reachable; model {model!r} not in pulled list ({len(models)} available)"
        elif model and model in models:
            preview = f"reachable; model {model!r} available"
        return {"rawTextPreview": preview[:100]}
