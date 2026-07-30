"""Ollama LLM provider — local/unauthenticated HTTP API via httpx.

Uses native ``/api/tags`` and ``/api/chat`` (not the OpenAI-compat ``/v1`` layer)
so structured output can pass a JSON schema through ``format``. Context window
defaults to ``OLLAMA_NUM_CTX`` (32768) because Ollama's stock window silently
truncates long resume+job prompts — too small a value cuts mid-JSON or drops
the front of the prompt with no error.
"""

from typing import Any

import httpx

from app.config import get_settings
from app.llm.base import LlmProvider, parse_json_response


class OllamaProvider(LlmProvider):
    provider_name = "ollama"

    def __init__(self, base_url: str | None = None) -> None:
        settings = get_settings()
        # config.ollama_base_url always has a default; callers may override per request.
        self.base_url = (base_url or settings.ollama_base_url).strip().rstrip("/")
        self._generate_timeout = settings.ollama_timeout_seconds
        self._connect_timeout = settings.ollama_connect_timeout_seconds
        self._num_ctx = settings.ollama_num_ctx

    def _headers(self, api_key: str) -> dict[str, str]:
        # Local Ollama needs no auth; a non-empty key is only for LAN proxies /
        # future optional tokens (stored encrypted like other providers).
        # Content-Type is set by httpx when json= is passed.
        if api_key:
            return {"Authorization": f"Bearer {api_key}"}
        return {}

    def _client(self, timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url, timeout=timeout, headers={"Accept": "application/json"}
        )

    async def _chat(
        self,
        api_key: str,
        model: str,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        fmt: object | None = None,
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
        if fmt is not None:
            body["format"] = fmt
        async with self._client(self._generate_timeout) as client:
            response = await client.post("/api/chat", json=body, headers=self._headers(api_key))
            response.raise_for_status()
            payload = response.json()
        message = payload.get("message") or {}
        content = message.get("content") if isinstance(message, dict) else None
        return str(content or "").strip()

    async def list_models(self, api_key: str) -> list[str]:
        async with self._client(self._connect_timeout) as client:
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
        return await self._chat(api_key, model, system_prompt, user_prompt, max_tokens)

    async def generate_json(
        self,
        api_key: str,
        model: str,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, Any] | None = None,
        max_tokens: int = 2000,
    ) -> dict[str, Any]:
        text = await self._chat(
            api_key,
            model,
            system_prompt,
            user_prompt,
            max_tokens,
            fmt=response_schema if response_schema is not None else "json",
        )
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
