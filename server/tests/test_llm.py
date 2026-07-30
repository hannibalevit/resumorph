import json
from types import SimpleNamespace

import httpx
import pytest
from app.config import get_settings
from app.llm.base import parse_json_response
from app.llm.claude_provider import ClaudeProvider
from app.llm.factory import get_llm_provider
from app.llm.gemini_provider import GeminiProvider
from app.llm.ollama_provider import OllamaProvider
from app.llm.openai_provider import OpenAiProvider
from app.prompt_loader import render_prompt
from app.services.llm_settings import normalize_base_url, resolve_ollama_base_url
from fastapi import HTTPException

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
    assert isinstance(get_llm_provider("ollama"), OllamaProvider)
    assert get_llm_provider("ollama", base_url="http://example:11434").base_url == (
        "http://example:11434"
    )


def test_get_llm_provider_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="Unsupported LLM provider"):
        get_llm_provider("mystery")


def test_ollama_prompt_files_load_and_substitute() -> None:
    """Files exist, load, and every $placeholder is substituted (safe_substitute
    would otherwise leave unknown names in the text and still look like a pass)."""
    for task in ("job_scan", "tailored_resume", "cover_letter", "field_answer"):
        prompt = render_prompt(
            "ollama",
            task,
            job_context_schema="{}",
            url="https://example.com",
            title="Role",
            headings=[],
            page_text="text",
            tailored_resume_schema="{}",
            job_context_json="{}",
            base_resume="resume",
            cover_letter_schema="{}",
            role="Engineer",
            company="Acme",
            today="1 January 2026",
            resume="resume",
            question="Why?",
            max_length=200,
            field_answer_schema="{}",
            field_type="textarea",
            placeholder="(none)",
            nearby_text="(none)",
            current_value="(empty)",
        )
        assert prompt.system
        assert prompt.user
        assert "$" not in prompt.system
        assert "$" not in prompt.user


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


# ---------------------------------------------------------------------------
# OllamaProvider
# ---------------------------------------------------------------------------


class _FakeHttpxResponse:
    def __init__(self, payload: object, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.request = httpx.Request("GET", "http://localhost:11434/")

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"Client error {self.status_code}",
                request=self.request,
                response=httpx.Response(self.status_code, request=self.request),
            )

    def json(self) -> object:
        return self._payload


class _FakeHttpxClient:
    def __init__(
        self,
        *,
        get_payload=None,
        post_payload=None,
        get_status: int = 200,
        post_status: int = 200,
    ) -> None:
        self.get_payload = get_payload or {"models": []}
        self.post_payload = post_payload or {"message": {"content": "{}"}}
        self.get_status = get_status
        self.post_status = post_status
        self.calls: list[tuple[str, str, dict[str, object] | None]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def get(self, path: str, headers: dict[str, str] | None = None):
        self.calls.append(("GET", path, None))
        response = _FakeHttpxResponse(self.get_payload, self.get_status)
        response.request = httpx.Request("GET", f"http://localhost:11434{path}")
        return response

    async def post(self, path: str, json: dict[str, object] | None = None, headers=None):
        self.calls.append(("POST", path, json))
        response = _FakeHttpxResponse(self.post_payload, self.post_status)
        response.request = httpx.Request("POST", f"http://localhost:11434{path}")
        return response


def _patch_ollama_httpx(
    monkeypatch,
    *,
    get_payload=None,
    post_payload=None,
    get_status: int = 200,
    post_status: int = 200,
):
    client = _FakeHttpxClient(
        get_payload=get_payload,
        post_payload=post_payload,
        get_status=get_status,
        post_status=post_status,
    )
    timeouts: list[float] = []

    def factory(*args: object, **kwargs: object):
        timeout = kwargs.get("timeout")
        if isinstance(timeout, (int, float)):
            timeouts.append(float(timeout))
        return client

    monkeypatch.setattr("app.llm.ollama_provider.httpx.AsyncClient", factory)
    client.timeouts = timeouts  # type: ignore[attr-defined]
    return client


async def test_ollama_list_models(monkeypatch) -> None:
    client = _patch_ollama_httpx(
        monkeypatch,
        get_payload={
            "models": [
                {"name": "llama3.2:latest"},
                {"name": "mistral"},
                {"model": ""},
                "not-a-dict",
                42,
                None,
            ]
        },
    )
    models = await OllamaProvider(base_url="http://localhost:11434").list_models("")
    assert models == ["llama3.2:latest", "mistral"]
    assert client.timeouts == [10.0]  # type: ignore[attr-defined]


async def test_ollama_generate_json_uses_schema_format(monkeypatch) -> None:
    client = _patch_ollama_httpx(
        monkeypatch, post_payload={"message": {"content": '```json\n{"ok": true}\n```'}}
    )
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}}
    result = await OllamaProvider(base_url="http://localhost:11434/").generate_json(
        "", "llama3.2", "sys", "user", response_schema=schema, max_tokens=128
    )
    assert result == {"ok": True}
    assert client.calls[0][0] == "POST"
    body = client.calls[0][2]
    assert body is not None
    assert body["format"] == schema
    assert body["stream"] is False
    assert body["options"]["num_ctx"] == 32768
    assert body["options"]["num_predict"] == 128
    assert client.timeouts == [300.0]  # type: ignore[attr-defined]


async def test_ollama_generate_json_surfaces_http_error_when_model_missing(
    monkeypatch,
) -> None:
    """Pulled-model miss is usually a non-2xx from /api/chat (e.g. 404)."""
    _patch_ollama_httpx(monkeypatch, post_status=404, post_payload={"error": "model not found"})
    with pytest.raises(httpx.HTTPStatusError) as exc:
        await OllamaProvider(base_url="http://localhost:11434").generate_json(
            "", "missing-model", "sys", "user"
        )
    assert exc.value.response.status_code == 404


async def test_ollama_list_models_surfaces_http_error(monkeypatch) -> None:
    _patch_ollama_httpx(monkeypatch, get_status=503, get_payload={"error": "unavailable"})
    with pytest.raises(httpx.HTTPStatusError) as exc:
        await OllamaProvider(base_url="http://localhost:11434").list_models("")
    assert exc.value.response.status_code == 503


async def test_ollama_settings_from_env_reach_client(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_NUM_CTX", "16384")
    monkeypatch.setenv("OLLAMA_TIMEOUT_SECONDS", "120")
    monkeypatch.setenv("OLLAMA_CONNECT_TIMEOUT_SECONDS", "7")
    get_settings.cache_clear()

    client = _patch_ollama_httpx(
        monkeypatch, post_payload={"message": {"content": '{"ok": true}'}}
    )
    provider = OllamaProvider(base_url="http://localhost:11434")
    assert provider._num_ctx == 16384
    assert provider._generate_timeout == 120.0
    assert provider._connect_timeout == 7.0

    await provider.generate_json("", "llama3.2", "sys", "user")
    assert client.calls[0][2] is not None
    assert client.calls[0][2]["options"]["num_ctx"] == 16384
    assert client.timeouts == [120.0]  # type: ignore[attr-defined]

    await provider.list_models("")
    assert client.timeouts == [120.0, 7.0]  # type: ignore[attr-defined]

    get_settings.cache_clear()


async def test_ollama_generate_text_sends_bearer_when_key_present(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class CapturingClient(_FakeHttpxClient):
        async def post(self, path: str, json: dict[str, object] | None = None, headers=None):
            captured["headers"] = headers
            return await super().post(path, json=json, headers=headers)

    client = CapturingClient(post_payload={"message": {"content": " hi "}})
    monkeypatch.setattr("app.llm.ollama_provider.httpx.AsyncClient", lambda *a, **k: client)
    text = await OllamaProvider(base_url="http://localhost:11434").generate_text(
        "proxy-token", "llama3.2", "sys", "user"
    )
    assert text == "hi"
    assert captured["headers"]["Authorization"] == "Bearer proxy-token"


async def test_ollama_test_connection(monkeypatch) -> None:
    _patch_ollama_httpx(monkeypatch, get_payload={"models": [{"name": "llama3.2"}]})
    result = await OllamaProvider(base_url="http://localhost:11434").test_connection("", "llama3.2")
    assert "llama3.2" in result["rawTextPreview"]


async def test_ollama_generate_json_rejects_empty_content(monkeypatch) -> None:
    _patch_ollama_httpx(monkeypatch, post_payload={"message": {"content": "  "}})
    with pytest.raises(ValueError, match="empty chat response"):
        await OllamaProvider(base_url="http://localhost:11434").generate_json(
            "", "llama3.2", "sys", "user"
        )


async def test_ollama_generate_json_without_schema_uses_json_format(monkeypatch) -> None:
    client = _patch_ollama_httpx(monkeypatch, post_payload={"message": {"content": '{"a": 1}'}})
    result = await OllamaProvider(base_url="http://localhost:11434").generate_json(
        "", "llama3.2", "sys", "user"
    )
    assert result == {"a": 1}
    assert client.calls[0][2] is not None
    assert client.calls[0][2]["format"] == "json"


async def test_ollama_generate_text_omits_bearer_without_key(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class CapturingClient(_FakeHttpxClient):
        async def post(self, path: str, json: dict[str, object] | None = None, headers=None):
            captured["headers"] = headers
            return await super().post(path, json=json, headers=headers)

    client = CapturingClient(post_payload={"message": {"content": "ok"}})
    monkeypatch.setattr("app.llm.ollama_provider.httpx.AsyncClient", lambda *a, **k: client)
    await OllamaProvider(base_url="http://localhost:11434").generate_text(
        "", "llama3.2", "sys", "user"
    )
    assert captured["headers"] == {}


def test_normalize_base_url_strips_slash_and_rejects_bad_scheme() -> None:
    assert normalize_base_url("http://localhost:11434/") == "http://localhost:11434"
    with pytest.raises(HTTPException) as exc:
        normalize_base_url("ftp://localhost:11434")
    assert exc.value.status_code == 422


def test_normalize_base_url_drops_query_fragment_and_rejects_credentials() -> None:
    assert (
        normalize_base_url("http://localhost:11434/v1?x=1#frag") == "http://localhost:11434/v1"
    )
    with pytest.raises(HTTPException) as exc:
        normalize_base_url("http://user:pass@localhost:11434")
    assert exc.value.status_code == 422
    assert "credentials" in str(exc.value.detail).lower()


def test_resolve_ollama_base_url_prefers_saved(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.llm_settings.settings.ollama_base_url",
        "http://host.docker.internal:11434",
    )
    assert resolve_ollama_base_url("http://10.0.0.1:11434/") == "http://10.0.0.1:11434"
    assert resolve_ollama_base_url(None) == "http://host.docker.internal:11434"
    assert resolve_ollama_base_url("  ") == "http://host.docker.internal:11434"


def test_resolve_ollama_base_url_whitespace_env_falls_back(monkeypatch) -> None:
    monkeypatch.setattr("app.services.llm_settings.settings.ollama_base_url", "   ")
    assert resolve_ollama_base_url(None) == "http://localhost:11434"
