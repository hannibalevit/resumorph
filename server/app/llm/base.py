import json
from abc import ABC, abstractmethod
from typing import Any


def parse_json_response(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```json").removeprefix("```").strip()
        cleaned = cleaned.removesuffix("```").strip()

    decoder = json.JSONDecoder()
    start_candidates = [index for index, character in enumerate(cleaned) if character in "{["]
    for start in start_candidates:
        try:
            value, _ = decoder.raw_decode(cleaned[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
        if isinstance(value, list):
            return {"items": value}
    raise json.JSONDecodeError("No JSON object found", cleaned, 0)


class LlmProvider(ABC):
    provider_name: str

    @abstractmethod
    async def test_connection(self, api_key: str, model: str | None = None) -> dict[str, Any]: ...

    @abstractmethod
    async def list_models(self, api_key: str) -> list[str]: ...

    @abstractmethod
    async def generate_json(
        self,
        api_key: str,
        model: str,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, Any] | None = None,
        max_tokens: int = 2000,
    ) -> dict[str, Any]: ...

    @abstractmethod
    async def generate_text(
        self, api_key: str, model: str, system_prompt: str, user_prompt: str, max_tokens: int = 2000
    ) -> str: ...
