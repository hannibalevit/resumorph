import json
from types import SimpleNamespace

import pytest
from app.llm.base import parse_json_response
from app.llm.claude_provider import ClaudeProvider
from app.llm.factory import get_llm_provider
from app.llm.gemini_provider import GeminiProvider
from app.llm.openai_provider import OpenAiProvider

# ---------------------------------------------------------------------------
# base.parse_json_response
# ---------------------------------------------------------------------------


def test_parse_json_response_plain_object() -> None:
    assert parse_json_response('{"a": 1}') == {"a": 1}


def test_parse_json_response_strips_code_fence() -> None:
    assert parse_json_response('```json\n{"a": 1}\n```') == {"a": 1}


def test_parse_json_response_wraps_top_level_list() -> None:
    assert parse_json_response("[1, 2, 3]") == {"items": [1, 2, 3]}


def test_parse_json_response_finds_object_inside_prose() -> None:
    assert parse_json_response('Here you go: {"a": 1} thanks') == {"a": 1}


def test_parse_json_response_raises_on_no_json() -> None:
    with pytest.raises(json.JSONDecodeError):
        parse_json_response("no json here")


# ---------------------------------------------------------------------------
# factory
# ---------------------------------------------------------------------------


def test_get_llm_provider_returns_matching_implementations() -> None:
    assert isinstance(get_llm_provider("openai"), OpenAiProvider)
    assert isinstance(get_llm_provider("gemini"), GeminiProvider)
    assert isinstance(get_llm_provider("claude"), ClaudeProvider)


def test_get_llm_provider_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="Unsupported LLM provider"):
        get_llm_provider("mystery")


# ---------------------------------------------------------------------------
# OpenAiProvider
# ---------------------------------------------------------------------------


class _FakeOpenAIResponses:
    def __init__(self, outputs: list[str]) -> None:
        self._outputs = outputs
        self.calls = 0
        self.received_kwargs: list[dict[str, object]] = []

    async def create(self, **kwargs: object):
        value = self._outputs[min(self.calls, len(self._outputs) - 1)]
        self.calls += 1
        self.received_kwargs.append(kwargs)
        return SimpleNamespace(output_text=value)


class _FakeOpenAIModels:
    def __init__(self, ids: list[str]) -> None:
        self._ids = ids

    async def list(self):
        return SimpleNamespace(data=[SimpleNamespace(id=item) for item in self._ids])


def _patch_openai(monkeypatch, *, outputs=None, ids=None):
    responses = _FakeOpenAIResponses(outputs or ["{}"])
    models = _FakeOpenAIModels(ids or [])

    def factory(*args: object, **kwargs: object):
        return SimpleNamespace(responses=responses, models=models)

    monkeypatch.setattr("app.llm.openai_provider.AsyncOpenAI", factory)
    return responses


async def test_openai_generate_text(monkeypatch) -> None:
    _patch_openai(monkeypatch, outputs=["  hello  "])
    text = await OpenAiProvider().generate_text("k", "gpt", "sys", "user")
    assert text == "hello"


async def test_openai_generate_json_direct(monkeypatch) -> None:
    _patch_openai(monkeypatch, outputs=['{"ok": true}'])
    result = await OpenAiProvider().generate_json("k", "gpt", "sys", "user")
    assert result == {"ok": True}


async def test_openai_generate_json_retries_when_empty(monkeypatch) -> None:
    responses = _patch_openai(monkeypatch, outputs=["", '{"retry": 1}'])
    result = await OpenAiProvider().generate_json(
        "k", "gpt", "sys", "user", response_schema={"type": "object"}
    )
    assert result == {"retry": 1}
    assert responses.calls == 2


async def test_openai_list_models_filters_and_sorts(monkeypatch) -> None:
    _patch_openai(
        monkeypatch,
        ids=["gpt-4o", "gpt-4o-audio", "o3-mini", "text-embedding-3", "gpt-4.1"],
    )
    models = await OpenAiProvider().list_models("k")
    assert models == ["gpt-4.1", "gpt-4o", "o3-mini"]


async def test_openai_test_connection(monkeypatch) -> None:
    _patch_openai(monkeypatch, outputs=["ok"])
    result = await OpenAiProvider().test_connection("k")
    assert result == {"rawTextPreview": "ok"}


async def test_openai_generate_text_constrains_reasoning_effort_for_reasoning_models(
    monkeypatch,
) -> None:
    responses = _patch_openai(monkeypatch, outputs=["ok"])
    await OpenAiProvider().generate_text("k", "gpt-5.6-sol", "sys", "user")
    assert responses.received_kwargs[0]["reasoning"] == {"effort": "low"}


async def test_openai_generate_text_omits_reasoning_effort_for_non_reasoning_models(
    monkeypatch,
) -> None:
    responses = _patch_openai(monkeypatch, outputs=["ok"])
    await OpenAiProvider().generate_text("k", "gpt-4.1-mini", "sys", "user")
    assert "reasoning" not in responses.received_kwargs[0]


# ---------------------------------------------------------------------------
# ClaudeProvider
# ---------------------------------------------------------------------------


def _patch_claude(monkeypatch, *, blocks=None, model_ids=None):
    content = blocks if blocks is not None else [SimpleNamespace(text="hi")]

    class Messages:
        async def create(self, **kwargs: object):
            return SimpleNamespace(content=content)

    class Models:
        async def list(self, **kwargs: object):
            return SimpleNamespace(data=[SimpleNamespace(id=item) for item in (model_ids or [])])

    def factory(*args: object, **kwargs: object):
        return SimpleNamespace(messages=Messages(), models=Models())

    monkeypatch.setattr("app.llm.claude_provider.AsyncAnthropic", factory)


async def test_claude_generate_text_joins_text_blocks(monkeypatch) -> None:
    _patch_claude(
        monkeypatch,
        blocks=[SimpleNamespace(text="Hello "), SimpleNamespace(text="world"), object()],
    )
    text = await ClaudeProvider().generate_text("k", "claude", "sys", "user")
    assert text == "Hello world"


async def test_claude_generate_json(monkeypatch) -> None:
    _patch_claude(monkeypatch, blocks=[SimpleNamespace(text='{"a": 1}')])
    assert await ClaudeProvider().generate_json("k", "claude", "sys", "user") == {"a": 1}


async def test_claude_list_models(monkeypatch) -> None:
    _patch_claude(monkeypatch, model_ids=["claude-3-5-sonnet", "gpt-4", "claude-3-haiku"])
    models = await ClaudeProvider().list_models("k")
    assert models == ["claude-3-5-sonnet", "claude-3-haiku"]


async def test_claude_test_connection(monkeypatch) -> None:
    _patch_claude(monkeypatch, blocks=[SimpleNamespace(text="ok")])
    assert await ClaudeProvider().test_connection("k") == {"rawTextPreview": "ok"}


# ---------------------------------------------------------------------------
# GeminiProvider
# ---------------------------------------------------------------------------


def _patch_gemini(monkeypatch, *, text="hi", items=None):
    class Models:
        async def generate_content(self, **kwargs: object):
            return SimpleNamespace(text=text)

        async def list(self):
            return items or []

    def factory(*args: object, **kwargs: object):
        return SimpleNamespace(aio=SimpleNamespace(models=Models()))

    monkeypatch.setattr("app.llm.gemini_provider.genai.Client", factory)


async def test_gemini_generate_text(monkeypatch) -> None:
    _patch_gemini(monkeypatch, text="  answer  ")
    assert await GeminiProvider().generate_text("k", "gemini", "sys", "user") == "answer"


async def test_gemini_generate_json(monkeypatch) -> None:
    _patch_gemini(monkeypatch, text='{"a": 1}')
    assert await GeminiProvider().generate_json("k", "gemini", "sys", "user") == {"a": 1}


async def test_gemini_list_models_filters(monkeypatch) -> None:
    items = [
        SimpleNamespace(name="models/gemini-2.5-flash", supported_actions=["generateContent"]),
        SimpleNamespace(name="models/gemini-imagen", supported_actions=["generateContent"]),
        SimpleNamespace(name="models/gemini-2.0-pro", supported_actions=["embedContent"]),
    ]
    _patch_gemini(monkeypatch, items=items)
    models = await GeminiProvider().list_models("k")
    assert models == ["gemini-2.5-flash"]


async def test_gemini_test_connection(monkeypatch) -> None:
    _patch_gemini(monkeypatch, text="ok")
    assert await GeminiProvider().test_connection("k") == {"rawTextPreview": "ok"}
