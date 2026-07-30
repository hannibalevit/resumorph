# ResuMorph Backend

FastAPI backend for the ResuMorph Chrome extension.

## Setup

Dependencies are managed with [uv](https://docs.astral.sh/uv/) (Python 3.12 or 3.13).

```bash
uv sync              # create .venv and install runtime deps
uv sync --dev        # ...including test deps (pytest, ruff, mypy, …)
cp .env.example .env
```

Edit `.env` and set `MASTER_ENCRYPTION_KEY` to a Fernet key (`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`) — this encrypts the LLM provider API keys at rest. You don't need to put a provider API key in `.env`: OpenAI/Gemini/Claude keys are entered later through the extension's Settings panel and stored encrypted in the local SQLite database, never in an env var. (The optional `OPENAI_API_KEY` env var only powers the deprecated non-session `POST /api/generate-resume` endpoint in `routers/legacy.py`.)

For **Ollama**, set `OLLAMA_BASE_URL` (default `http://localhost:11434`) and optionally
`OLLAMA_TIMEOUT_SECONDS` (generation, default 300), `OLLAMA_CONNECT_TIMEOUT_SECONDS`
(list/test only, default 10 — so a unreachable host fails fast), and `OLLAMA_NUM_CTX`.
**`OLLAMA_NUM_CTX` defaults to `32768`** — resume/cover-letter prompts are large, and if
the window is too small Ollama truncates **silently** (mid-JSON parse failures, or dropped
prompt prefix with no error). Do not treat a lower value as a safe “tested default.” Under
Docker, compose sets `OLLAMA_BASE_URL=http://host.docker.internal:11434` and
`OLLAMA_NUM_CTX`; if Ollama only binds `127.0.0.1`, the container still cannot reach it
until you change `OLLAMA_HOST` (prefer the Docker bridge address over `0.0.0.0` — see
root `SECURITY.md`).

## Run

```bash
uv run uvicorn app.main:app --reload --port 8000
```

## Test

```bash
uv run pytest
```

## Lint, format & type-check

```bash
uv run ruff check .        # lint (add --fix to autofix)
uv run ruff format .       # format (add --check for CI)
uv run mypy                # static type check
uv run deptry .            # unused / missing / misplaced dependencies
```

Configuration for all three lives in `pyproject.toml` (`[tool.ruff]`, `[tool.mypy]`, `[tool.deptry]`).

## Managing dependencies

```bash
uv add <package>              # runtime dependency
uv add --dev <package>        # dev/test dependency
uv lock --upgrade             # refresh uv.lock
```

## Check

```bash
curl http://localhost:8000/health
```

## Privacy

The backend stores your base resume and scanned job postings locally in SQLite (`UserProfileModel.base_resume_text`, `JobSessionModel.job_context_json`) so tailored resumes, cover letters, and field answers stay consistent across a session — none of this leaves your machine except as part of an LLM request you configure. Provider API keys are Fernet-encrypted at rest and never round-trip to the client in plaintext. Cloud providers (OpenAI, Gemini, Claude) are called with your key; **Ollama** uses a configurable `base_url` (no key for local use) and can keep generation fully on-machine. Do not log full resumes or job descriptions in production.
