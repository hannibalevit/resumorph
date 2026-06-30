# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Chrome Side Panel extension ("Resume Tailor") that tailors a user's resume to a job posting using an LLM, plus a local FastAPI + SQLite backend. The backend runs in Docker on `localhost:8000`; all user data (resume text, job sessions, encrypted API keys) stays on the user's machine. Only the LLM API call leaves the machine.

Two independent projects in one repo:
- `extension/` — TypeScript Chrome MV3 extension (Vite build, React side panel)
- `server/` — Python FastAPI backend (SQLAlchemy + SQLite)

## Commands

### Backend (run from `server/`, after `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`)
```bash
cp .env.example .env            # then set MASTER_ENCRYPTION_KEY (Fernet key) and an LLM key
uvicorn app.main:app --reload --port 8000
curl http://localhost:8000/health
```
There is no test suite in this repo currently (no `tests/` directory, no `pytest` config, no extension test runner).

### Docker (run from repo root)
```bash
make up              # docker compose up -d --build, serves on :8000
make down
make restart
make logs
make clean           # WARNING: deletes the data volume (DB + encryption key)
```
`server/entrypoint.sh` auto-generates `MASTER_ENCRYPTION_KEY` into the `/data` volume on first run if one isn't supplied.

### Extension (run from `extension/`)
```bash
npm install
npm run build         # tsc --noEmit && vite build -> extension/dist/
npm run dev            # vite dev mode
```
Or from repo root: `make build-extension`. Load `extension/dist` as an unpacked extension via `chrome://extensions`. Reload the extension after every rebuild.

There's no lint script configured; `npm run build` runs `tsc --noEmit` (strict mode, `noUnusedLocals`/`noUnusedParameters` on) before bundling, so type errors and unused symbols fail the build.

## Architecture

### Backend (`server/app/`)

`main.py` is a single-file FastAPI app holding all routes (no router modules). Key building blocks it composes:

- **`models.py`** — SQLAlchemy models: `UserProfileModel` (single row, id `"local-user"`, holds the base resume text), `JobSessionModel` (one per canonical job posting), `GeneratedArtifactModel` (resumes/cover letters/field answers produced for a session), `LlmProviderConfigModel` (per-provider encrypted API key + settings), `AppSettingsModel` (single row, id `"local-settings"`, default + per-task provider/model), `JobRelatedLinkModel`.
- **`app.on_event("startup")`** runs a hand-rolled additive migration: it diffs each table's current columns against a hardcoded dict and runs `ALTER TABLE ADD COLUMN` for anything missing. There is no Alembic — if you add a column to a model, also add it to the `migrations` dict in `main.py` or existing SQLite DBs won't pick it up.
- **LLM provider abstraction** (`llm/`): `LlmProvider` ABC (`base.py`) with `OpenAiProvider`, `GeminiProvider`, `ClaudeProvider` implementations, selected via `llm/factory.py::get_llm_provider(name)`. Every provider implements `test_connection`, `list_models`, `generate_json` (schema-constrained), `generate_text`.
- **Per-task LLM routing**: each generation task (`scan`, `resume`, `field_answer`) can have its own provider/model override stored on `AppSettingsModel`, falling back to the global default provider. `resolve_task_llm(db, task)` / `resolve_default_llm(db)` in `main.py` implement this fallback chain — use these rather than reading `AppSettingsModel` fields directly.
- **Prompts** (`prompts/<provider>/<task>.{system,user}.md`) are plain `string.Template` files, one set per provider per task (`job_scan`, `tailored_resume`, `cover_letter`, `field_answer`, plus an `openai/legacy_tailored_resume`). `prompt_loader.py::render_prompt(provider, task, **values)` loads and substitutes them. When adding a new task or provider, you must add a matching `.system.md`/`.user.md` pair for all three providers or `render_prompt` raises `FileNotFoundError`.
- **Secrets**: provider API keys are Fernet-encrypted at rest (`security.py`) using `MASTER_ENCRYPTION_KEY`; only a masked preview (`mask_secret`) ever round-trips to the client.
- **Job identity**: `job_service.py::canonical_job_key` / `normalize_url` dedupe job postings so re-scanning the same posting updates the existing `JobSessionModel` instead of creating duplicates. `match_current_page` lets the extension associate an application-form page (different URL) with an already-scanned job session by normalized URL or title containment.
- Errors are raised via the `fail(status_code, code, message, **details)` helper, producing a consistent `{"error": {"code", "message", "details"}}` body (see `http_exception_handler`).
- A legacy non-session endpoint `POST /api/generate-resume` (`validation.py` + `resume_generator.py` + `openai_client.py`) still exists alongside the newer session-based `/api/job-sessions/*` flow — don't assume it's dead code.

### Extension (`extension/src/`)

MV3 with three entry points built by `vite.config.ts` (`rollupOptions.input`): `serviceWorker` (background), `pageAssistant` (content script, runs on every page), and three HTML UIs (`popup`, `upload`, `sidepanel` — sidepanel is the primary UI, opened via the action icon).

- **`background/serviceWorker.ts`** — owns action icon/badge state and is the message hub: listens for `chrome.runtime.onMessage` (`COLOR_SCHEME_CHANGED`, `SET_ACTIVE_JOB_SESSION`/`GET_ACTIVE_JOB_SESSION`, `GENERATE_FIELD_ANSWER`) and proxies `GENERATE_FIELD_ANSWER` straight to the backend (used by content scripts that can't easily import the API client).
- **`shared/apiClient.ts`** — the single source of truth for backend REST calls (`api.*`); also defines the TS response/request types used across the UI. New backend endpoints should get a corresponding `api.*` entry here rather than ad-hoc `fetch` calls.
- **`shared/storage.ts`** — wraps `chrome.storage.local` for the few persisted prefs (`baseResume`, `apiBaseUrl`, `onboardingComplete`, `extensionEnabled`). `apiBaseUrl` defaults to `http://localhost:8000` and is user-overridable in Settings — code should always go through `getApiBaseUrl()`, never hardcode the base URL.
- **`content/jobExtraction/`** — a fallback cascade for pulling job-posting text out of an arbitrary page, tried in order (`extractJobFromPage.ts`): (1) user-selected text ≥300 chars, (2) JSON-LD `JobPosting` schema, (3) per-site extractor (`siteExtractors/` — linkedin, greenhouse, lever, ashby, indeed, smartRecruiters, workable, generic), (4) generic DOM scoring (`domScoring.ts`), (5) raw visible-text fallback. Each stage reports a `confidence` and the result also carries `debug` info for troubleshooting bad extractions. When adding support for a new job site, add a new file under `siteExtractors/` and register it in `siteExtractors/index.ts` rather than special-casing it elsewhere.
- **`content/formDetector.ts` / `inlineAssistant.ts` / `pageAssistant.ts`** — the in-page "AI" button feature on application form fields. Sensitive fields (password/payment/ID/demographic) are explicitly excluded and must stay excluded — the backend also independently rejects `field.is_sensitive` in `generate_field_answer` as a second line of defense, so don't remove either check without removing both.
- **`sidepanel/`** — the React UI (`App.tsx` is the main view, plus `OnboardingView`, `SettingsView`, `HistoryView`). No state management library; state is local React state plus the storage helpers above.

### Cross-cutting conventions

- The extension never auto-submits forms or scans pages without an explicit user action (click "Scan this page" / click the inline AI button on a field). Preserve this when touching content scripts.
- Backend CORS is locked to `chrome-extension://` origins via `allow_origin_regex` plus `ALLOWED_ORIGINS` env var — don't loosen this without understanding the privacy model (see README "How it works").
- JSON field naming: Pydantic schemas use `by_alias=True` (camelCase on the wire) while Python/SQLAlchemy stay snake_case; TS types in `apiClient.ts`/`sidepanelTypes.ts` mirror the camelCase wire format.
