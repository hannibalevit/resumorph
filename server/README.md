# Resume Tailor Backend

FastAPI backend for the Resume Tailor Chrome extension.

## Setup

Use Python 3.12 or 3.13 for the MVP environment.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and set `OPENAI_API_KEY`.

## Run

```bash
uvicorn app.main:app --reload --port 8000
```

## Check

```bash
curl http://localhost:8000/health
```

## Privacy

The backend does not store resumes or job text. It can parse uploaded `.doc` files for the extension and sends the submitted resume and job page text to the configured OpenAI-compatible API provider when generating the tailored resume. Do not log full resumes or job descriptions in production.
