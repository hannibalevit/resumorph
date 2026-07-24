from typing import Any

from anthropic import AsyncAnthropic
from anthropic.types import TextBlockParam

from app.llm.base import LlmProvider, parse_json_response


class ClaudeProvider(LlmProvider):
    provider_name = "claude"

    async def generate_text(
        self, api_key: str, model: str, system_prompt: str, user_prompt: str, max_tokens: int = 2000
    ) -> str:
        client = AsyncAnthropic(api_key=api_key)
        # Task system prompts (prompt_loader.py) are static per provider+task - identical
        # on every call - so caching the prefix lets repeat calls within the 5-minute TTL
        # skip re-processing it, cutting both latency and cost. A longer 1h TTL exists only
        # on the beta cache_control param (client.beta.messages.create + the
        # extended-cache-ttl-2025-04-11 header) - not worth the beta surface here.
        system: list[TextBlockParam] = [
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ]
        response = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            # Newer models (e.g. claude-sonnet-5) default to adaptive thinking when this
            # is omitted, which can consume the whole max_tokens budget on reasoning and
            # leave no room for the actual response. This provider never reads thinking
            # blocks, so keep it off.
            thinking={"type": "disabled"},
            messages=[{"role": "user", "content": user_prompt}],
        )
        return "".join(block.text for block in response.content if hasattr(block, "text")).strip()

    async def list_models(self, api_key: str) -> list[str]:
        page = await AsyncAnthropic(api_key=api_key).models.list(limit=100)
        return sorted(item.id for item in page.data if item.id.startswith("claude-"))

    async def generate_json(
        self,
        api_key: str,
        model: str,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, Any] | None = None,
        max_tokens: int = 2000,
    ) -> dict[str, Any]:
        text = await self.generate_text(
            api_key, model, system_prompt, f"{user_prompt}\n\nReturn valid JSON only.", max_tokens
        )
        return parse_json_response(text)

    async def test_connection(self, api_key: str, model: str | None = None) -> dict[str, Any]:
        text = await self.generate_text(
            api_key, model or "claude-haiku-4-5-20251001", "Reply with exactly: ok", "ok", 8
        )
        return {"rawTextPreview": text[:50]}
