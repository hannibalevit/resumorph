# Resume Tailor Backend

FastAPI backend for the Resume Tailor Chrome extension.

## Setup

Dependencies are managed with [uv](https://docs.astral.sh/uv/) (Python 3.12 or 3.13).

```bash
uv sync              # create .venv and install runtime deps
uv sync --dev        # ...including test deps (pytest, httpx)
cp .env.example .env
```

Edit `.env` and set `OPENAI_API_KEY`.

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

The backend does not store resumes or job text. It can parse uploaded `.doc` files for the extension and sends the submitted resume and job page text to the configured OpenAI-compatible API provider when generating the tailored resume. Do not log full resumes or job descriptions in production.
