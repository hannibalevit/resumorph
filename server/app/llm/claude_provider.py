from typing import Any

from anthropic import AsyncAnthropic

from app.llm.base import LlmProvider, parse_json_response
from app.llm.claude_cli import (
    CLI_MODEL_CATALOG,
    cli_generate_json,
    cli_generate_text,
    cli_list_models,
    is_oauth_token,
)


class ClaudeProvider(LlmProvider):
    provider_name = "claude"

    async def generate_text(
        self, api_key: str, model: str, system_prompt: str, user_prompt: str, max_tokens: int = 2000
    ) -> str:
        if is_oauth_token(api_key):
            return await cli_generate_text(api_key, model, system_prompt, user_prompt, max_tokens)
        client = AsyncAnthropic(api_key=api_key)
        response = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return "".join(block.text for block in response.content if hasattr(block, "text")).strip()

    async def list_models(self, api_key: str) -> list[str]:
        if is_oauth_token(api_key):
            return cli_list_models()
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
        if is_oauth_token(api_key):
            return await cli_generate_json(
                api_key, model, system_prompt, user_prompt, response_schema, max_tokens
            )
        text = await self.generate_text(
            api_key, model, system_prompt, f"{user_prompt}\n\nReturn valid JSON only.", max_tokens
        )
        return parse_json_response(text)

    async def test_connection(self, api_key: str, model: str | None = None) -> dict[str, Any]:
        default_model = (
            CLI_MODEL_CATALOG[0] if is_oauth_token(api_key) else "claude-3-5-haiku-latest"
        )
        text = await self.generate_text(
            api_key, model or default_model, "Reply with exactly: ok", "ok", 8
        )
        return {"rawTextPreview": text[:50]}
