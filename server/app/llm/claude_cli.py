"""Claude Code CLI subprocess path, used when the stored Claude secret is a
Claude Pro/Max subscription OAuth token (``sk-ant-oat01-...``) rather than a
regular Anthropic API key. Shells out to the real ``claude`` CLI binary in
non-interactive print mode (``claude -p``) — Anthropic's own documented,
sanctioned mechanism for using ``CLAUDE_CODE_OAUTH_TOKEN`` outside an
interactive session. Direct HTTP calls to the Messages API with an OAuth
token are blocked server-side and prohibited by Anthropic's Consumer ToS.
"""

import asyncio
import json
import os
import tempfile
from collections.abc import Callable
from typing import Any

from app.llm.base import parse_json_response

OAUTH_TOKEN_PREFIX = "sk-ant-oat01-"

# The CLI has no flag to list available models programmatically, so this is a
# small hardcoded catalog of current model IDs, used only in OAuth-token mode.
CLI_MODEL_CATALOG = [
    "claude-opus-4-8",
    "claude-sonnet-5",
    "claude-haiku-4-5",
]

_CLI_BINARY = "claude"
_CLI_TIMEOUT_SECONDS = 120.0

# The CLI refuses --permission-mode bypassPermissions (and --dangerously-skip-
# permissions) outright when it detects it's running as root/sudo, as a hard
# safety check with no override flag. Our Docker image has no USER directive
# (the app itself keeps running as root — changing that would break existing
# users' /data volume permissions), so only the CLI subprocess is dropped to
# this unprivileged system user, created in the Dockerfile.
_CLI_UNPRIVILEGED_USER = os.environ.get("CLAUDE_CLI_RUN_AS_USER", "claudecli")


class ClaudeCliError(RuntimeError):
    """The `claude` CLI subprocess failed, timed out, or returned output that
    doesn't match the expected `--output-format json` shape."""


def is_oauth_token(value: str) -> bool:
    return value.startswith(OAUTH_TOKEN_PREFIX)


def _drop_privileges_uid_gid() -> tuple[int, int] | None:
    """(uid, gid) to run the CLI subprocess as when we're root; None (no-op)
    everywhere else, e.g. local dev outside Docker."""
    if os.name != "posix" or os.geteuid() != 0:
        return None
    import pwd

    try:
        entry = pwd.getpwnam(_CLI_UNPRIVILEGED_USER)
    except KeyError:
        return None
    return entry.pw_uid, entry.pw_gid


def _preexec_drop_privileges(uid: int, gid: int) -> Callable[[], None]:
    """Built for the child process's `preexec_fn`, called there after fork but
    before exec. Using `preexec_fn` (run in-process by the event loop's
    subprocess implementation) rather than `subprocess.Popen`'s `user`/`group`
    kwargs, because uvloop — installed transitively by `uvicorn[standard]` and
    used as the running loop in both Docker and local dev — implements its own
    subprocess transport that doesn't recognize those kwargs and rejects any
    call passing them (even as `None`) with "unexpected kwargs: user, group"."""

    def _drop() -> None:
        os.setgroups([])
        os.setgid(gid)
        os.setuid(uid)

    return _drop


async def _invoke(
    oauth_token: str,
    *,
    model: str,
    system_prompt: str,
    user_prompt: str,
    json_schema: dict[str, Any] | None,
) -> dict[str, Any]:
    args = [
        _CLI_BINARY,
        "-p",
        user_prompt,
        "--output-format",
        "json",
        "--system-prompt",
        system_prompt,
        "--model",
        model,
        "--max-turns",
        "1",
        "--no-session-persistence",
        "--disallowed-tools",
        "*",
        "--permission-mode",
        "bypassPermissions",
    ]
    if json_schema is not None:
        args += ["--json-schema", json.dumps(json_schema)]

    with tempfile.TemporaryDirectory(prefix="claude-cli-") as isolated_dir:
        drop_privileges = _drop_privileges_uid_gid()
        if drop_privileges is not None:
            os.chown(isolated_dir, *drop_privileges)
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": isolated_dir,
            "CLAUDE_CODE_OAUTH_TOKEN": oauth_token,
            "DISABLE_AUTOUPDATER": "1",
            "DISABLE_UPDATES": "1",
            # Skips auto-update/telemetry/error-reporting/feedback/release-notes network
            # checks the CLI otherwise makes on every invocation. Cannot use --bare instead
            # (see module docstring) — --bare stops reading OAuth tokens entirely and
            # requires an ANTHROPIC_API_KEY, defeating the point of this module.
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
            # `claude -p` normally fires a background small/fast-model request per
            # invocation just to generate a session title we never read (title only
            # matters for --continue/--resume, and we pass --no-session-persistence).
            # This skips that extra model call.
            "CLAUDE_CODE_DISABLE_TERMINAL_TITLE": "1",
        }
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                cwd=isolated_dir,
                env=env,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                preexec_fn=(
                    _preexec_drop_privileges(*drop_privileges)
                    if drop_privileges is not None
                    else None
                ),
            )
        except FileNotFoundError as exc:
            raise ClaudeCliError(
                "The `claude` CLI binary is not installed in this container."
            ) from exc

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=_CLI_TIMEOUT_SECONDS
            )
        except TimeoutError as exc:
            proc.kill()
            await proc.wait()
            raise ClaudeCliError("Claude CLI timed out.") from exc

    # The CLI exits non-zero even for well-formed errors (e.g. an invalid or
    # expired OAuth token) while still writing a JSON `is_error`/`result`
    # payload to stdout and leaving stderr empty — so stdout must be parsed
    # *before* trusting the exit code, or that payload's actual error message
    # is lost in favor of an uninformative "exited with code 1: ".
    try:
        payload: dict[str, Any] = json.loads(stdout.decode())
    except json.JSONDecodeError as exc:
        if proc.returncode != 0:
            raise ClaudeCliError(
                f"Claude CLI exited with code {proc.returncode}: "
                f"{stderr.decode(errors='replace').strip()[:500]}"
            ) from exc
        raise ClaudeCliError("Claude CLI returned non-JSON output.") from exc
    if payload.get("is_error"):
        raise ClaudeCliError(str(payload.get("result") or payload)[:500])
    if proc.returncode != 0:
        raise ClaudeCliError(
            f"Claude CLI exited with code {proc.returncode}: "
            f"{stderr.decode(errors='replace').strip()[:500]}"
        )
    return payload


async def cli_generate_text(
    oauth_token: str, model: str, system_prompt: str, user_prompt: str, max_tokens: int = 2000
) -> str:
    hinted_prompt = f"{user_prompt}\n\n(Keep the response under about {max_tokens} tokens.)"
    payload = await _invoke(
        oauth_token,
        model=model,
        system_prompt=system_prompt,
        user_prompt=hinted_prompt,
        json_schema=None,
    )
    return str(payload.get("result", "")).strip()


async def cli_generate_json(
    oauth_token: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    response_schema: dict[str, Any] | None,
    max_tokens: int = 2000,
) -> dict[str, Any]:
    if response_schema is not None:
        try:
            payload = await _invoke(
                oauth_token,
                model=model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                json_schema=response_schema,
            )
            structured = payload.get("structured_output")
            if isinstance(structured, dict):
                return structured
        except ClaudeCliError:
            pass  # fall back to text+parse below (e.g. schema shape rejected)
    text = await cli_generate_text(
        oauth_token, model, system_prompt, f"{user_prompt}\n\nReturn valid JSON only.", max_tokens
    )
    return parse_json_response(text)


def cli_list_models() -> list[str]:
    return list(CLI_MODEL_CATALOG)
