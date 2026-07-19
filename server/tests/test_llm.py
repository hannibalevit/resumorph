import json
import os
from types import SimpleNamespace

import pytest
from app.llm import claude_cli
from app.llm.base import parse_json_response
from app.llm.claude_cli import CLI_MODEL_CATALOG, ClaudeCliError, cli_generate_json, is_oauth_token
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

    async def create(self, **kwargs: object):
        value = self._outputs[min(self.calls, len(self._outputs) - 1)]
        self.calls += 1
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
# ClaudeProvider — OAuth token (Claude Code CLI subprocess) path
# ---------------------------------------------------------------------------

OAUTH_TOKEN = "sk-ant-oat01-fake-token"


def test_is_oauth_token() -> None:
    assert is_oauth_token(OAUTH_TOKEN) is True
    assert is_oauth_token("sk-ant-api03-regular-key") is False


def _patch_cli_subprocess(
    monkeypatch, *, stdout: bytes, returncode: int = 0, captured: dict | None = None
):
    class FakeProcess:
        def __init__(self) -> None:
            self.returncode = returncode
            self.killed = False

        async def communicate(self):
            return stdout, b"boom"

        def kill(self) -> None:
            self.killed = True

        async def wait(self) -> None:
            return None

    async def fake_exec(*args: object, **kwargs: object):
        if captured is not None:
            captured["args"] = args
            captured["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr("app.llm.claude_cli.asyncio.create_subprocess_exec", fake_exec)


async def test_claude_cli_generate_text(monkeypatch) -> None:
    _patch_cli_subprocess(monkeypatch, stdout=json.dumps({"result": "hi there"}).encode())
    text = await ClaudeProvider().generate_text(OAUTH_TOKEN, "claude-sonnet-5", "sys", "user")
    assert text == "hi there"


async def test_claude_cli_generate_json_uses_structured_output(monkeypatch) -> None:
    _patch_cli_subprocess(monkeypatch, stdout=json.dumps({"structured_output": {"a": 1}}).encode())
    result = await ClaudeProvider().generate_json(
        OAUTH_TOKEN, "claude-sonnet-5", "sys", "user", response_schema={"type": "object"}
    )
    assert result == {"a": 1}


async def test_claude_cli_generate_json_falls_back_without_schema(monkeypatch) -> None:
    _patch_cli_subprocess(monkeypatch, stdout=json.dumps({"result": '{"a": 2}'}).encode())
    result = await ClaudeProvider().generate_json(OAUTH_TOKEN, "claude-sonnet-5", "sys", "user")
    assert result == {"a": 2}


async def test_claude_cli_list_models() -> None:
    models = await ClaudeProvider().list_models(OAUTH_TOKEN)
    assert models == CLI_MODEL_CATALOG


async def test_claude_cli_test_connection(monkeypatch) -> None:
    _patch_cli_subprocess(monkeypatch, stdout=json.dumps({"result": "ok"}).encode())
    assert await ClaudeProvider().test_connection(OAUTH_TOKEN) == {"rawTextPreview": "ok"}


async def test_claude_cli_nonzero_exit_raises(monkeypatch) -> None:
    _patch_cli_subprocess(monkeypatch, stdout=b"", returncode=1)
    with pytest.raises(ClaudeCliError, match="exited with code 1"):
        await ClaudeProvider().generate_text(OAUTH_TOKEN, "claude-sonnet-5", "sys", "user")


async def test_claude_cli_invalid_json_stdout_raises(monkeypatch) -> None:
    _patch_cli_subprocess(monkeypatch, stdout=b"not json")
    with pytest.raises(ClaudeCliError, match="non-JSON output"):
        await ClaudeProvider().generate_text(OAUTH_TOKEN, "claude-sonnet-5", "sys", "user")


async def test_claude_cli_is_error_payload_raises(monkeypatch) -> None:
    _patch_cli_subprocess(
        monkeypatch, stdout=json.dumps({"is_error": True, "result": "token expired"}).encode()
    )
    with pytest.raises(ClaudeCliError, match="token expired"):
        await ClaudeProvider().generate_text(OAUTH_TOKEN, "claude-sonnet-5", "sys", "user")


async def test_claude_cli_nonzero_exit_with_is_error_json_uses_result_message(monkeypatch) -> None:
    # The real CLI exits non-zero for auth failures (e.g. an invalid/expired
    # OAuth token) while still writing a well-formed is_error/result payload
    # to stdout and leaving stderr empty — that message must win over the
    # generic "exited with code N" fallback.
    _patch_cli_subprocess(
        monkeypatch,
        stdout=json.dumps(
            {
                "is_error": True,
                "result": "Failed to authenticate. API Error: 401 Invalid bearer token",
            }
        ).encode(),
        returncode=1,
    )
    with pytest.raises(ClaudeCliError, match="Failed to authenticate"):
        await ClaudeProvider().generate_text(OAUTH_TOKEN, "claude-sonnet-5", "sys", "user")


async def test_claude_cli_nonzero_exit_with_valid_non_error_json_raises(monkeypatch) -> None:
    _patch_cli_subprocess(
        monkeypatch, stdout=json.dumps({"result": "partial"}).encode(), returncode=2
    )
    with pytest.raises(ClaudeCliError, match="exited with code 2"):
        await ClaudeProvider().generate_text(OAUTH_TOKEN, "claude-sonnet-5", "sys", "user")


async def test_claude_cli_missing_binary_raises(monkeypatch) -> None:
    async def fake_exec(*args: object, **kwargs: object):
        raise FileNotFoundError

    monkeypatch.setattr("app.llm.claude_cli.asyncio.create_subprocess_exec", fake_exec)
    with pytest.raises(ClaudeCliError, match="not installed"):
        await ClaudeProvider().generate_text(OAUTH_TOKEN, "claude-sonnet-5", "sys", "user")


async def test_claude_cli_timeout_kills_process(monkeypatch) -> None:
    killed = {"value": False}

    class HangingProcess:
        returncode = None

        async def communicate(self):
            raise TimeoutError

        def kill(self) -> None:
            killed["value"] = True

        async def wait(self) -> None:
            return None

    async def fake_exec(*args: object, **kwargs: object):
        return HangingProcess()

    monkeypatch.setattr("app.llm.claude_cli.asyncio.create_subprocess_exec", fake_exec)
    monkeypatch.setattr("app.llm.claude_cli._CLI_TIMEOUT_SECONDS", 0.01)
    with pytest.raises(ClaudeCliError, match="timed out"):
        await ClaudeProvider().generate_text(OAUTH_TOKEN, "claude-sonnet-5", "sys", "user")
    assert killed["value"] is True


async def test_claude_cli_generate_json_falls_back_when_no_structured_output(monkeypatch) -> None:
    async def fake_invoke(oauth_token, *, model, system_prompt, user_prompt, json_schema):
        if json_schema is not None:
            return {"result": "ignored"}
        return {"result": '{"a": 3}'}

    monkeypatch.setattr("app.llm.claude_cli._invoke", fake_invoke)
    result = await cli_generate_json(
        OAUTH_TOKEN, "claude-sonnet-5", "sys", "user", response_schema={"type": "object"}
    )
    assert result == {"a": 3}


async def test_claude_cli_generate_json_falls_back_on_schema_error(monkeypatch) -> None:
    async def fake_invoke(oauth_token, *, model, system_prompt, user_prompt, json_schema):
        if json_schema is not None:
            raise ClaudeCliError("schema rejected")
        return {"result": '{"a": 4}'}

    monkeypatch.setattr("app.llm.claude_cli._invoke", fake_invoke)
    result = await cli_generate_json(
        OAUTH_TOKEN, "claude-sonnet-5", "sys", "user", response_schema={"type": "object"}
    )
    assert result == {"a": 4}


async def test_claude_cli_oauth_token_not_leaked_to_parent_environ(monkeypatch) -> None:
    captured: dict = {}
    _patch_cli_subprocess(
        monkeypatch, stdout=json.dumps({"result": "hi"}).encode(), captured=captured
    )
    await ClaudeProvider().generate_text(OAUTH_TOKEN, "claude-sonnet-5", "sys", "user")
    assert captured["kwargs"]["env"]["CLAUDE_CODE_OAUTH_TOKEN"] == OAUTH_TOKEN
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in os.environ


# ---------------------------------------------------------------------------
# ClaudeProvider — dropping root privileges for the CLI subprocess
#
# The `claude` binary refuses --permission-mode bypassPermissions outright
# when it detects it's running as root/sudo ("cannot be used with root/sudo
# privileges for security reasons") — a hard safety check with no override
# flag, confirmed against the real CLI in a container. Our Docker image runs
# as root (no USER directive), so the subprocess must be dropped to an
# unprivileged user instead.
# ---------------------------------------------------------------------------


def test_drop_privileges_uid_gid_noop_when_not_root(monkeypatch) -> None:
    monkeypatch.setattr("app.llm.claude_cli.os.geteuid", lambda: 1000)
    assert claude_cli._drop_privileges_uid_gid() is None


def test_drop_privileges_uid_gid_noop_when_configured_user_missing(monkeypatch) -> None:
    monkeypatch.setattr("app.llm.claude_cli.os.geteuid", lambda: 0)

    def fake_getpwnam(name: str):
        raise KeyError(name)

    monkeypatch.setattr("pwd.getpwnam", fake_getpwnam)
    assert claude_cli._drop_privileges_uid_gid() is None


def test_drop_privileges_uid_gid_returns_uid_gid_when_root(monkeypatch) -> None:
    monkeypatch.setattr("app.llm.claude_cli.os.geteuid", lambda: 0)
    monkeypatch.setattr("pwd.getpwnam", lambda name: SimpleNamespace(pw_uid=999, pw_gid=999))
    assert claude_cli._drop_privileges_uid_gid() == (999, 999)


async def test_claude_cli_no_privilege_drop_when_not_root(monkeypatch) -> None:
    monkeypatch.setattr("app.llm.claude_cli.os.geteuid", lambda: 1000)
    chowned = {"called": False}
    monkeypatch.setattr("app.llm.claude_cli.os.chown", lambda *a: chowned.update(called=True))
    captured: dict = {}
    _patch_cli_subprocess(
        monkeypatch, stdout=json.dumps({"result": "hi"}).encode(), captured=captured
    )
    await ClaudeProvider().generate_text(OAUTH_TOKEN, "claude-sonnet-5", "sys", "user")
    assert "user" not in captured["kwargs"]
    assert "group" not in captured["kwargs"]
    assert captured["kwargs"].get("preexec_fn") is None
    assert chowned["called"] is False


async def test_claude_cli_drops_privileges_and_chowns_tempdir_when_root(monkeypatch) -> None:
    # `preexec_fn` (not the `user`/`group` Popen kwargs) is how privileges get
    # dropped, because uvloop's subprocess transport — the loop actually
    # running under uvicorn[standard] — rejects `user`/`group` kwargs outright
    # ("unexpected kwargs: user, group"), even when passed as None.
    monkeypatch.setattr("app.llm.claude_cli.os.geteuid", lambda: 0)
    monkeypatch.setattr("pwd.getpwnam", lambda name: SimpleNamespace(pw_uid=999, pw_gid=999))
    chowned: dict = {}
    monkeypatch.setattr(
        "app.llm.claude_cli.os.chown",
        lambda path, uid, gid: chowned.update(path=path, uid=uid, gid=gid),
    )
    dropped: dict = {}
    monkeypatch.setattr(
        "app.llm.claude_cli.os.setgroups", lambda groups: dropped.update(groups=groups)
    )
    monkeypatch.setattr("app.llm.claude_cli.os.setgid", lambda gid: dropped.update(gid=gid))
    monkeypatch.setattr("app.llm.claude_cli.os.setuid", lambda uid: dropped.update(uid=uid))
    captured: dict = {}
    _patch_cli_subprocess(
        monkeypatch, stdout=json.dumps({"result": "hi"}).encode(), captured=captured
    )
    await ClaudeProvider().generate_text(OAUTH_TOKEN, "claude-sonnet-5", "sys", "user")
    assert "user" not in captured["kwargs"]
    assert "group" not in captured["kwargs"]
    assert chowned == {"path": captured["kwargs"]["cwd"], "uid": 999, "gid": 999}

    captured["kwargs"]["preexec_fn"]()
    assert dropped == {"groups": [], "gid": 999, "uid": 999}


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
