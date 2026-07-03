from typing import Any

from google import genai
from google.genai import types

from app.llm.base import LlmProvider, parse_json_response


class GeminiProvider(LlmProvider):
    provider_name = "gemini"

    async def generate_text(
        self, api_key: str, model: str, system_prompt: str, user_prompt: str, max_tokens: int = 2000
    ) -> str:
        client = genai.Client(api_key=api_key)
        response = await client.aio.models.generate_content(
            model=model,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt, max_output_tokens=max_tokens, temperature=0
            ),
        )
        return (response.text or "").strip()

    async def list_models(self, api_key: str) -> list[str]:
        client = genai.Client(api_key=api_key)
        pager = await client.aio.models.list()
        excluded = ("image", "imagen", "veo", "embedding", "aqa", "tts", "live", "audio")
        return sorted(
            name
            # AsyncPager has no __iter__ but does define __getitem__, so it is
            # sync-iterable over the current page via the sequence protocol.
            for item in pager  # type: ignore[attr-defined]
            if "generateContent" in (getattr(item, "supported_actions", None) or [])
            for name in [str(item.name).removeprefix("models/")]
            if name.startswith("gemini-") and not any(term in name for term in excluded)
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
        text = await self.generate_text(
            api_key, model, system_prompt, f"{user_prompt}\n\nReturn valid JSON only.", max_tokens
        )
        return parse_json_response(text)

    async def test_connection(self, api_key: str, model: str | None = None) -> dict[str, Any]:
        text = await self.generate_text(
            api_key, model or "gemini-2.5-flash-lite", "Reply with exactly: ok", "ok", 8
        )
        return {"rawTextPreview": text[:50]}
