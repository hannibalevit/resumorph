---
name: add-llm-task-or-provider
description: Use when adding a new LLM-invoking task (like scan/resume/field_answer) or a new LLM provider (like openai/gemini/claude), or adding/editing a prompt. Missing a single prompt file for one provider raises FileNotFoundError at request time, not at startup.
---

# Add an LLM task or provider

Prompts live at `server/app/prompts/<provider>/<task>.{system,user}.md`, plain
`string.Template` files loaded by `prompt_loader.py::render_prompt(provider, task, **values)`.
There is no fallback — a missing file raises `FileNotFoundError` the first time
that provider+task combination is actually requested, which may be well after
the code change that introduced it.

## Adding a new task (e.g. a 4th task beyond scan/resume/field_answer)

1. Create `<task>.system.md` and `<task>.user.md` under **all three** provider
   directories: `server/app/prompts/claude/`, `.../gemini/`, `.../openai/`.
   That's 6 files minimum for one new task.
2. Add the task name to the `LlmTaskName` Literal in `server/app/schemas.py`.
3. Add the orchestration function in `server/app/services/generation.py`
   (follow the shape of `run_job_scan` / `build_resume` — call
   `resolve_task_llm(db, task)` then `get_llm_provider(name)`, never import a
   provider class directly).
4. If the task needs per-task provider override support in Settings, check
   `services/llm_settings.py::resolve_task_llm` picks it up (it's driven by
   the `AppSettingsModel` fields — may need a new field, which also needs the
   `add-db-column` flow if it's a new column).
5. Add a router endpoint if user-facing (see `add-backend-endpoint`).

## Adding a new provider (rarer — a 4th LLM provider beyond openai/gemini/claude)

Same idea, more surface: a `prompts/<provider>/` dir mirroring every existing
task file, a new `LlmProvider` subclass in `server/app/llm/` (see `llm/base.py`
for the ABC, `llm/claude_provider.py` as reference), a branch in
`llm/factory.py::get_llm_provider`, the provider name added to the
`ProviderName` Literal in `schemas.py`, and the SDK dep via `uv add <sdk>`.

## Verify

`uv run pytest` — the `stub_llm` fixture pattern in
`tests/test_api_endpoints.py` patches `resolve_task_llm` and
`get_llm_provider` on `app.services.generation` (not on the provider module
itself), so new tasks are exercised without hitting a real LLM. Also smoke-test
`render_prompt` directly for the new provider/task pair to confirm all files
resolve.

## Gotchas

- `render_prompt` is `lru_cache`d — if you edit a prompt file's content
  during an interactive `uv run uvicorn --reload` session, the cache may
  still serve the old content; restart the server to confirm.
- Prompt files are `.strip()`-ped and substituted with `Template.safe_substitute`,
  which silently leaves unknown `$placeholders` in place instead of raising —
  double-check every `$var` in a new prompt is actually passed by the caller.
