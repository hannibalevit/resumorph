# AGENTS.md

Durable instructions for Codex when working in this repository.

## Project Purpose

ResuMorph is a local-first Chrome Side Panel extension plus a local FastAPI backend. It scans a user-selected job page, stores resume/job/session data in a local SQLite database, and uses a configured LLM provider (OpenAI, Gemini, Claude, or local Ollama) to generate tailored resumes, cover letters, and application-field answers. Cloud LLM API requests leave the machine; with Ollama on a local URL, generation can stay fully on-device. API keys are encrypted at rest.

## Architecture

- `extension/`: Chrome MV3 extension built with TypeScript, Vite, React, and Vitest.
  - `src/background/`: service worker, action/badge state, message hub.
  - `src/content/`: page scanning, job extraction, form detection, inline AI field assistance.
  - `src/content/jobExtraction/`: extraction cascade and site-specific extractors.
  - `src/shared/apiClient.ts`: single source for backend REST calls and wire types.
  - `src/shared/storage.ts`: Chrome storage helpers, including user-overridable API base URL.
  - `src/sidepanel/`: primary React UI.
- `server/`: FastAPI backend using SQLAlchemy, SQLite, Pydantic, uv, Ruff, Mypy, Deptry, and Pytest.
  - `app/main.py`: app factory, CORS, lifespan migration, router registration.
  - `app/routers/`: route modules by resource.
  - `app/models.py`: SQLAlchemy models.
  - `app/db_migrations.py`: additive SQLite migrations; there is no Alembic.
  - `app/schemas.py`: Pydantic API models with camelCase aliases.
  - `app/serializers.py`: model-to-schema mapping.
  - `app/services/generation.py`: LLM-invoking orchestration.
  - `app/llm/`: provider abstraction and provider implementations.
  - `app/prompts/<provider>/`: provider/task prompt templates.
- `extension/dist/`: built extension output included for loading in Chrome. Do not hand-edit built assets unless explicitly asked.

## Commands

Backend commands run from `server/`:

```bash
uv sync --dev
uv run uvicorn app.main:app --reload --port 8000
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run deptry .
uv run pytest
```

Extension commands run from `extension/`:

```bash
npm install
npm test
npm run build
```

Repo-level commands:

```bash
make up
make down
make restart
make logs
make build-extension
```

`make clean` deletes the Docker data volume, including the SQLite DB and encryption key. Do not run it unless the user explicitly asks to wipe local data.

## Coding Standards

- Keep backend code typed and formatted by Ruff. Line length is 100; use `ruff format` rather than manual wrapping.
- Keep Python/SQLAlchemy names snake_case and API wire fields camelCase.
- Use `ApiModel` plus `Field(alias="camelCase")` for Pydantic request/response models.
- Use existing routers, service modules, serializers, helpers, and storage/API wrappers before adding new abstractions.
- Keep FastAPI route handlers `async def`.
- Raise API errors with `fail(status_code, code, message, **details)` from `server/app/errors.py`; do not return ad-hoc error shapes.
- Do not add ad-hoc `fetch` calls in the extension; add backend calls to `extension/src/shared/apiClient.ts`.
- Do not hardcode the backend base URL in extension code; use `getApiBaseUrl()`.
- For new job sites, add a site extractor under `extension/src/content/jobExtraction/siteExtractors/` and register it in `index.ts`.
- Do not bypass `services/llm_settings.py` for provider/model selection.
- Put LLM generation orchestration in `server/app/services/generation.py`, not in routers or provider classes.

## Data, Privacy, And Security

- Treat resumes, job descriptions, generated artifacts, application answers, provider API keys, and `MASTER_ENCRYPTION_KEY` as sensitive.
- Never print, log, commit, or expose full resumes, job descriptions, API keys, Fernet keys, or `server/.env`.
- Provider API keys must remain encrypted at rest through `server/app/security.py`; only masked previews may return to clients.
- Preserve explicit user action before scanning pages or generating field answers.
- The extension must never auto-submit forms, click Apply/Next, or modify sensitive fields automatically.
- Sensitive fields such as password, payment, government ID, and demographic fields must remain excluded in both extension detection and backend validation.
- Do not loosen CORS from the current Chrome-extension/local model without a specific user request and a privacy review.
- Do not add broad Chrome extension permissions unless the feature requires them and the reason is documented.
- Do not create, paste, or commit secrets, tokens, `.env` contents, or encryption keys.

## Backend Rules

- New endpoints belong in the matching module under `server/app/routers/`, or in a new router imported and registered in `main.py`.
- Request/response schemas belong in `schemas.py`; model-to-response conversion belongs in `serializers.py`.
- If a model column is added in `models.py`, add the matching SQL column to `MIGRATIONS` in `db_migrations.py`.
- Migrations are additive only through `ALTER TABLE ADD COLUMN`; renames, drops, and type changes require a separate explicit plan.
- If an API shape is consumed by the extension, update the matching TypeScript type and `api.*` method.
- Stub LLM calls in tests by patching names imported by `app.services.generation`, not the provider module.
- `.github/workflows/server-ci.yml` runs the same ruff/mypy/deptry/pytest gate on every PR and every push to `main` (no `paths:` filter — the `main` ruleset requires its jobs as status checks, and a workflow that doesn't run leaves them pending forever). The `pull_request` trigger is what lets fork PRs report those checks at all; don't reduce either CI workflow back to `on: push`. Still run backend verification locally before finishing backend work — CI is a backstop, not a substitute for checking before you push.

## LLM And Prompt Rules

- Provider names and task names are validated by schema literals. Update the schema when adding providers/tasks.
- Prompt files are required for every supported provider/task pair at `server/app/prompts/<provider>/<task>.system.md` and `.user.md`.
- `prompt_loader.py::render_prompt` uses cached `string.Template` prompts and does not fail on unknown placeholders. Check placeholders manually when editing prompts.
- Do not send more user data to an LLM than the feature requires.
- Do not add an LLM provider without updating the provider class, factory, schemas, prompts, settings behavior, and tests.

## Testing Expectations

- Backend changes under `server/app` require, at minimum:
  - `uv run ruff check .`
  - `uv run ruff format --check .`
  - `uv run mypy`
  - `uv run deptry .`
  - `uv run pytest`
- Backend coverage must stay at or above the configured 85% gate.
- Extension changes require `npm test` and `npm run build` from `extension/`.
- Cross-boundary changes require both backend and extension checks.
- Add or update focused tests for changed behavior, especially API contracts, migrations, job extraction, sensitive-field exclusions, and LLM orchestration.

## Definition Of Done

- The implementation follows the existing architecture and ownership boundaries.
- Security and privacy constraints are preserved.
- API contracts are updated on both backend and extension sides when needed.
- Manual migrations and prompt coverage are complete when relevant.
- Tests and checks appropriate to the changed surface have been run, or any inability to run them is reported.
- The final response lists changed files, validation results, and remaining risks or assumptions.

## Review Checklist

- Are any secrets, resumes, job descriptions, or generated documents exposed in logs, tests, commits, or output?
- Does the extension still require explicit user action before scanning or field assistance?
- Are sensitive fields still excluded in extension code and backend validation?
- Are Pydantic aliases and TypeScript wire types still camelCase?
- Is any new router registered in `main.py`?
- Is any new model column present in `db_migrations.py`?
- Are all provider/task prompt files present?
- Are LLM calls centralized in `services/generation.py` and test-stubbable?
- Are extension permissions, CORS, and data flow still minimal?
- Were the right local checks run?

## Never Do

- Never delete or overwrite Claude instructions in `CLAUDE.md` or `.claude/`.
- Never run destructive data-wipe commands such as `make clean` or `docker compose down -v` without explicit user approval.
- Never stage or commit `server/.env`, encryption keys, local databases, generated coverage reports, or user data.
- Never weaken privacy protections, sensitive-field checks, encryption, or CORS casually.
- Never modify generated `extension/dist/` output instead of source unless explicitly requested.
- Never add dependencies without using the correct package manager and explaining why.
- Never invent MCP servers, config keys, external services, or hidden automation.

## Reporting Back

When finishing work, summarize:

- Files changed.
- Behavior or instruction changes made.
- Checks run and their results.
- Checks not run, with the reason.
- Assumptions, unresolved questions, or follow-up risks.
