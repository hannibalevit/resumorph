from typing import Any

from openai import AsyncOpenAI

from app.llm.base import LlmProvider, parse_json_response


class OpenAiProvider(LlmProvider):
    provider_name = "openai"

    async def generate_text(
        self, api_key: str, model: str, system_prompt: str, user_prompt: str, max_tokens: int = 2000
    ) -> str:
        client = AsyncOpenAI(api_key=api_key)
        response = await client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_output_tokens=max_tokens,
        )
        return response.output_text.strip()

    async def list_models(self, api_key: str) -> list[str]:
        models = await AsyncOpenAI(api_key=api_key).models.list()
        excluded = (
            "audio",
            "realtime",
            "transcribe",
            "tts",
            "image",
            "embedding",
            "moderation",
            "search",
        )
        return sorted(
            item.id
            for item in models.data
            if item.id.startswith(("gpt-", "o1", "o3", "o4"))
            and not any(term in item.id for term in excluded)
        )

    async def generate_json(
        self,
        api_key: str,
        model: str,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, Any] | None = None,
        max_tokens: int = 2000,
    ) -> dict[str, Any]:
        client = AsyncOpenAI(api_key=api_key)
        text_format: dict[str, Any] = {"type": "json_object"}
        if response_schema:
            text_format = {
                "type": "json_schema",
                "name": "structured_response",
                "schema": response_schema,
                "strict": False,
            }
        # The Responses API overloads type `input`/`text` as TypedDicts; plain dicts are
        # accepted at runtime but don't match the strict overload signatures.
        response = await client.responses.create(  # type: ignore[call-overload]
            model=model,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_output_tokens=max_tokens,
            text={"format": text_format},
        )
        text = response.output_text.strip()
        if text:
            return parse_json_response(text)

        retry = await client.responses.create(  # type: ignore[call-overload]
            model=model,
            input=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": (
                        f"{user_prompt}\n\nReturn exactly one valid JSON object and no other text."
                    ),
                },
            ],
            max_output_tokens=max_tokens,
            text={"format": text_format},
        )
        return parse_json_response(retry.output_text.strip())

    async def test_connection(self, api_key: str, model: str | None = None) -> dict[str, Any]:
        # Responses API requires at least 16 output tokens; this is still a minimal
        # connection check.
        text = await self.generate_text(
            api_key, model or "gpt-4.1-mini", "Reply with exactly: ok", "ok", 16
        )
        return {"rawTextPreview": text[:50]}
