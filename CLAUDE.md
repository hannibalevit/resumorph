# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Chrome Side Panel extension ("ResuMorph") that tailors a user's resume to a job posting using an LLM, plus a local FastAPI + SQLite backend. The backend runs in Docker on `localhost:8000`; all user data (resume text, job sessions, encrypted API keys) stays on the user's machine. Only the LLM API call leaves the machine.

Two independent projects in one repo:
- `extension/` — TypeScript Chrome MV3 extension (Vite build, React side panel)
- `server/` — Python FastAPI backend (SQLAlchemy + SQLite)

## Commands

### Backend (run from `server/`; dependencies managed with [uv](https://docs.astral.sh/uv/) — `pyproject.toml` + `uv.lock`)
```bash
uv sync --dev                   # create .venv and install runtime + test deps
cp .env.example .env            # then set MASTER_ENCRYPTION_KEY (Fernet key) and an LLM key
uv run uvicorn app.main:app --reload --port 8000
curl http://localhost:8000/health
```
Add deps with `uv add <pkg>` (runtime) or `uv add --dev <pkg>` (test); both update `uv.lock`. Backend tests live in `server/tests/` (pytest config in root `pytest.ini`); run them with `uv run pytest`. Coverage is on by default via `pytest-cov` (`--cov=app`): each run prints a per-file `term-missing` table and writes an HTML report to `server/htmlcov/` (open `index.html`). The suite fails if total coverage drops below 85% (`--cov-fail-under=85` in `pytest.ini`) — keep it green when adding backend code. Coverage settings live in `[tool.coverage.*]` in `server/pyproject.toml`.

Lint/format/type-check the backend with `uv run ruff check .`, `uv run ruff format .`, `uv run mypy`, and `uv run deptry .` (all configured in `server/pyproject.toml`; they must stay green). Ruff owns line length (100) — don't hand-wrap; let `ruff format` do it. When mypy needs a `str`→`Literal` narrowing at a validated boundary use `typing.cast`, and when a runtime-only dependency (e.g. `uvicorn`, `python-multipart`) trips deptry's DEP002, add it to `[tool.deptry.per_rule_ignores]` rather than importing it.

`.github/workflows/server-ci.yml` runs this same gate (ruff check/format, mypy, deptry, then pytest in an isolated Docker container, then a Docker image smoke test), separately from `.github/workflows/extension-ci.yml`. Both trigger on `pull_request` plus pushes to `main`, and both run unconditionally (no `paths:` filter) rather than being scoped to `server/**`/`extension/**` — the branch ruleset on `main` requires all 5 of their jobs as status checks, and any workflow that doesn't run leaves a required check stuck pending forever. That's also why `pull_request` is mandatory and can't be reduced back to `on: push`: a fork's commits are pushed to the fork, so no `push` event fires here and every contribution from outside the repo would be unmergeable. Fork-triggered runs get a read-only token and no secrets, so any job needing one (currently only `coverage-badge`) must stay gated on `github.event_name == 'push'`. Still run `ruff check`, `mypy`, `deptry`, and `pytest` locally before considering backend work done — CI is a backstop, not a substitute for checking before you push.

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

`npm test` runs Vitest (`extension/tests/`, jsdom env) — there is no separate lint script, but `npm run build` runs `tsc --noEmit` (strict mode, `noUnusedLocals`/`noUnusedParameters` on) before bundling, so type errors and unused symbols fail the build too. CI (`.github/workflows/extension-ci.yml`) runs `npm test` then `npm run build` on every PR and every push to `main` (no path filter — see the server-ci note above for why, and for why the `pull_request` trigger has to stay).

## Code navigation

If a `.codegraph/` directory exists at the repo root (created by running `codegraph init` — holds `codegraph.db` plus daemon files, already excluded from git via `.codegraph/.gitignore`), this repo is indexed by CodeGraph. When that directory is present and the CodeGraph MCP server (or the `codegraph` CLI) is available, prefer it over grep/find/reading files for locating or understanding code: the MCP tool `codegraph_explore` (or `codegraph explore "<question or symbol names>"` from the shell) answers most "where is X" / "how does X work" questions in a single call, returning verbatim source plus call paths between symbols — including dynamic-dispatch hops (callbacks, event listeners, JSX children) that grep can't follow. If `.codegraph/` is absent, skip CodeGraph entirely — indexing is an opt-in per-machine step, not a project requirement, and there's nothing to query.

## Architecture

### Backend (`server/app/`)

`main.py` is a thin app factory: it builds the `FastAPI` instance, wires CORS, registers the exception handler (`errors.py`), runs the startup migration via a `lifespan` context manager, and `include_router`s the route modules under `routers/`. Routes are split by resource into `routers/{health,settings,profile,job_sessions,artifacts,admin,legacy}.py` — add new endpoints to the matching router (or a new one wired into `main.py`) rather than back into `main.py`. Key building blocks the routers compose:

- **`models.py`** — SQLAlchemy models: `UserProfileModel` (single row, id `"local-user"`, holds the base resume text), `JobSessionModel` (one per canonical job posting), `GeneratedArtifactModel` (resumes/cover letters/field answers produced for a session), `LlmProviderConfigModel` (per-provider encrypted API key + settings), `AppSettingsModel` (single row, id `"local-settings"`, default + per-task provider/model), `JobRelatedLinkModel`.
- **`db_migrations.py`** runs a hand-rolled additive migration from the `lifespan` startup hook in `main.py`: it diffs each table's current columns against the hardcoded `MIGRATIONS` dict and runs `ALTER TABLE ADD COLUMN` for anything missing. There is no Alembic — if you add a column to a model, also add it to `MIGRATIONS` in `db_migrations.py` or existing SQLite DBs won't pick it up.
- **LLM provider abstraction** (`llm/`): `LlmProvider` ABC (`base.py`) with `OpenAiProvider`, `GeminiProvider`, `ClaudeProvider`, and `OllamaProvider` implementations, selected via `llm/factory.py::get_llm_provider(name, base_url=None)`. Cloud providers authenticate with a regular provider API key over that provider's HTTP SDK. Ollama is keyless (optional bearer only if a non-empty key is stored for a LAN proxy) and takes `base_url` from the factory; `resolve_task_llm` returns a 4-field `ResolvedLlm` NamedTuple (`provider`, `model`, `api_key`, `base_url`). `OllamaProvider.test_connection` deliberately *raises* when the host is reachable but has no models pulled, or when the requested model isn't in the pulled list — reachability alone is not a pass, since generation would 404. The route turns any exception from `test_connection` into `status: "failed"`, so this is the only lever a provider has to reject itself.
- **Per-task LLM routing**: each generation task (`scan`, `resume`, `field_answer`) can have its own provider/model override stored on `AppSettingsModel`, falling back to the global default provider. `resolve_task_llm(db, task)` / `resolve_default_llm(db)` in `services/llm_settings.py` implement this fallback chain — use these rather than reading `AppSettingsModel` fields directly.
- **Generation services** (`services/generation.py`) — all LLM-invoking orchestration (`run_job_scan`, `build_resume`, `build_cover_letter`, `generate_field_answer_content`) lives here; it is the single module referencing `get_llm_provider` + `resolve_task_llm` on the generation path (so tests stub the LLM by patching those two names on this module). Pure model→schema mappers live in `serializers.py`; pure string helpers in `text_utils.py`. `build_cover_letter` and `generate_field_answer_content` both call the shared `_latest_resume_text` helper, which prefers the session's most recently generated tailored-resume artifact over `profile.base_resume_text` — this keeps cover letters and field answers consistent with whatever resume was already tailored for that job, falling back to the base resume only if none has been generated yet.
- **Prompts** (`prompts/<provider>/<task>.{system,user}.md`) are plain `string.Template` files, one set per provider per task (`job_scan`, `tailored_resume`, `cover_letter`, `field_answer`, plus an `openai/legacy_tailored_resume`). `prompt_loader.py::render_prompt(provider, task, **values)` loads and substitutes them. When adding a new task or provider, you must add a matching `.system.md`/`.user.md` pair for every supported provider (`openai`, `gemini`, `claude`, `ollama`) or `render_prompt` raises `FileNotFoundError`.
- **Secrets**: provider API keys are Fernet-encrypted at rest (`security.py`) using `MASTER_ENCRYPTION_KEY`; only a masked preview (`mask_secret`) ever round-trips to the client.
- **Job identity**: `job_service.py::canonical_job_key` / `normalize_url` dedupe job postings so re-scanning the same posting updates the existing `JobSessionModel` instead of creating duplicates. `match_current_page` lets the extension associate an application-form page (different URL) with an already-scanned job session by normalized URL or title containment.
- Errors are raised via the `fail(status_code, code, message, **details)` helper in `errors.py`, producing a consistent `{"error": {"code", "message", "details"}}` body (see `http_exception_handler`, registered in `main.py`).
- A legacy non-session endpoint `POST /api/generate-resume` (`routers/legacy.py` + `validation.py` + `resume_generator.py` + `openai_client.py`) still exists alongside the newer session-based `/api/job-sessions/*` flow — don't assume it's dead code.

### Extension (`extension/src/`)

MV3 with three entry points built by `vite.config.ts` (`rollupOptions.input`): `serviceWorker` (background), `pageAssistant` (content script, runs on every page), and `sidepanel` (the only HTML UI — opened via the action icon, since `manifest.json`'s `side_panel.default_path` plus `chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true })` in `serviceWorker.ts` make it the sole entry point; there is no popup or separate upload page).

- **`background/serviceWorker.ts`** — owns action icon/badge state and is the message hub: listens for `chrome.runtime.onMessage` (`COLOR_SCHEME_CHANGED`, `SET_ACTIVE_JOB_SESSION`/`GET_ACTIVE_JOB_SESSION`, `GENERATE_FIELD_ANSWER`/`CANCEL_FIELD_ANSWER`) and proxies `GENERATE_FIELD_ANSWER` straight to the backend (used by content scripts that can't easily import the API client).
- **`background/keepAlive.ts`** — MV3 suspends an idle service worker after 30s, which would kill a field-answer generation mid-flight, so `withKeepAlive(work)` holds the worker open with the documented heartbeat (a trivial `chrome.runtime` call every 20s) and ref-counts concurrent generations. Chrome's *other* limit — 5 minutes for a single activity — cannot be reset, which is why the field-answer path times out at `MAX_ACTIVITY_MS` (270s) instead of the 330s the side panel uses: a self-inflicted timeout gives the user a real message, a killed worker just closes the message port. Any new long-running work in the service worker needs the same two things.
- **`shared/apiClient.ts`** — the single source of truth for backend REST calls (`api.*`); also defines the TS response/request types used across the UI. New backend endpoints should get a corresponding `api.*` entry here rather than ad-hoc `fetch` calls.
- **`shared/requestTimeout.ts`** — `withAbort(timeoutMs, externalSignal, send)` wraps every backend `fetch` (both `apiClient.ts` and the service worker's direct field-answer/health calls) in an `AbortController`, and maps the resulting bare `AbortError` to either `RequestTimeoutError` or `RequestCancelledError` so a user cancel isn't reported as a failure. Each tier (`PROBE_`/`TEST_`/`GENERATION_TIMEOUT_MS`) sits deliberately *above* the matching backend timeout in `app/config.py` so the backend's own error message wins; if you change a backend timeout, re-check the client tier above it. Generation calls (`scan`, `generateResume`, `generateCoverLetter`) take a `{ signal }` so the side panel's Cancel button and the inline assistant's second-click-to-cancel can abort them.
- **`shared/storage.ts`** — wraps `chrome.storage.local` for the few persisted prefs (`baseResume`, `apiBaseUrl`, `onboardingComplete`, `extensionEnabled`). `apiBaseUrl` defaults to `http://localhost:8000` and is user-overridable in Settings — code should always go through `getApiBaseUrl()`, never hardcode the base URL.
- **`content/jobExtraction/`** — a fallback cascade for pulling job-posting text out of an arbitrary page, orchestrated by `content/pageScanner.ts::getPrimaryJobText` and tried in order: (1) user-selected text ≥300 chars, (2) JSON-LD `JobPosting` schema, (3) per-site extractor (`siteExtractors/` — linkedin, greenhouse, lever, ashby, indeed, smartRecruiters, workable, generic), (4) generic DOM scoring (`domScoring.ts`), (5) raw visible-text fallback. Each stage reports a `confidence` and the result also carries `debug` info for troubleshooting bad extractions. When adding support for a new job site, add a new file under `siteExtractors/` and register it in `siteExtractors/index.ts` rather than special-casing it elsewhere.
- **`content/formDetector.ts` / `inlineAssistant.ts` / `pageAssistant.ts`** — the in-page "AI" button feature on application form fields. Sensitive fields (password/payment/ID/demographic) are explicitly excluded and must stay excluded — the backend also independently rejects `field.is_sensitive` in `generate_field_answer` as a second line of defense, so don't remove either check without removing both.
- **`sidepanel/`** — the React UI (`App.tsx` is the main view, plus `OnboardingView`, `SettingsView`, `HistoryView`). No state management library; state is local React state plus the storage helpers above. Onboarding and Settings report progress through `notice.tsx` (`useNotice` + `<NoticeLine>`) rather than a bare `.status` paragraph — call `notifyError` for anything that failed or blocks the user so it renders red with `role="alert"`, and `notify` for progress. A failure routed through `notify` is a bug: it renders as ordinary blue progress.

### Cross-cutting conventions

- The extension never auto-submits forms or scans pages without an explicit user action (click "Scan this page" / click the inline AI button on a field). Preserve this when touching content scripts.
- Backend CORS is locked to `chrome-extension://` origins via `allow_origin_regex` plus `ALLOWED_ORIGINS` env var — don't loosen this without understanding the privacy model (see README "How it works").
- JSON field naming: Pydantic schemas use `by_alias=True` (camelCase on the wire) while Python/SQLAlchemy stay snake_case; TS types in `apiClient.ts`/`sidepanelTypes.ts` mirror the camelCase wire format.

## On context compaction

If this conversation gets summarized, preserve:
- Which files have been read/edited so far this session and why (don't re-discover by re-reading everything).
- Any backend preflight results already obtained (ruff/mypy/deptry/pytest pass/fail) — don't silently re-run a clean check as if state is unknown.
- The specific router/model/prompt/migration files touched, if mid-way through the `add-db-column`, `add-llm-task-or-provider`, or `add-backend-endpoint` skill flows — these are multi-file changes and a half-applied one (e.g. model column added but `MIGRATIONS` dict not updated) is a real bug, not just lost context.
- Any user correction given this session about scope, style, or approach — these override the defaults above for the rest of the session.
