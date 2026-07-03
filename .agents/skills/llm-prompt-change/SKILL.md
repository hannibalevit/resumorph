---
name: llm-prompt-change
description: Use when adding or changing LLM tasks, providers, prompt templates, provider routing, or generation behavior.
---

# LLM Prompt Or Provider Change

## Workflow

1. Identify whether the change is a prompt edit, a new task, a new provider, or generation orchestration.
2. Keep LLM-invoking orchestration in `server/app/services/generation.py`.
3. Resolve provider/model choice through `services/llm_settings.py`; do not read settings fields directly.
4. For a new task, add `.system.md` and `.user.md` prompt files under every supported provider directory:
   - `server/app/prompts/claude/`
   - `server/app/prompts/gemini/`
   - `server/app/prompts/openai/`
5. For a new provider, add a provider implementation under `server/app/llm/`, register it in `llm/factory.py`, update provider literals in `schemas.py`, and add a full prompt directory matching existing tasks.
6. Update `LlmTaskName` or `ProviderName` literals in `server/app/schemas.py` when names change.
7. Check every `$placeholder` in changed prompts against the values passed to `render_prompt`.
8. Add tests that stub `resolve_task_llm` and `get_llm_provider` on `app.services.generation`.

## Validation

Run from `server/`:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run deptry .
```

For prompt additions, directly smoke-test `render_prompt(provider, task, **values)` for each provider/task pair.

## Common Failure Modes

- A prompt file is missing for one provider and fails later with `FileNotFoundError`.
- Unknown `$placeholders` remain because `Template.safe_substitute` does not raise.
- Prompt edits appear stale during local dev because `render_prompt` is cached.
- Provider/model routing is duplicated outside `services/llm_settings.py`.
- Tests patch the wrong module path and accidentally hit a real LLM.

## Expected Output

Report changed prompt files, generation/provider/schema changes, smoke-test coverage for provider/task pairs, and validation results.
