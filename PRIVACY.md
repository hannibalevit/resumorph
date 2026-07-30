# Privacy

**Last updated:** 2026-07-23

ResuMorph is built local-first: **there is no ResuMorph server**. You run
the backend yourself in Docker on your own machine, and the extension talks
only to that local backend. This document explains, concretely, what data
exists, where it lives, and the only path any of it can take off your
machine.

This is a plain-language technical explanation, not a legal privacy policy
issued by a company — this project has no company, no accounts, and no
servers of its own. If you deploy, modify, or redistribute ResuMorph
(e.g. host the backend somewhere other than your own machine), you are
responsible for your own compliance obligations for that deployment.

## Data controller / processor status (GDPR/CCPA)

Because no data is transmitted to or processed by any server operated by
this project, the maintainer does not act as a data controller or processor
under GDPR/CCPA (or similar regimes) for your resume, job, or account data —
**you are the sole controller of your own data on your own machine.** The
only processing outside your machine happens when your own backend sends a
request directly to the LLM provider you configured, using your own
credentials; that provider is a separate, independent data controller/
processor for whatever it receives, under its own privacy policy and terms.
If you fork or redeploy ResuMorph for other people to use (e.g. as a hosted
service), *you* take on whatever controller/processor role applies to that
deployment — this project's architecture doesn't do that work for you.

## What data exists, and where

Everything below lives in a single SQLite database inside the Docker volume
created by `docker-compose.yml` (`/data` in the container, a named `data`
volume on the host) — nowhere else:

| Data | Where it's stored | Notes |
|---|---|---|
| Your base resume text | `UserProfileModel` (SQLite) | Entered/uploaded once in the side panel |
| Scanned job posting text & metadata | `JobSessionModel` (SQLite) | One row per canonical job posting (deduplicated by URL/title) |
| Generated resumes, cover letters, field answers | `GeneratedArtifactModel` (SQLite) | Stored as base64 in the DB so they survive container restarts |
| LLM provider API keys | `LlmProviderConfigModel` (SQLite) | **Encrypted at rest** with Fernet (`server/app/security.py`) using `MASTER_ENCRYPTION_KEY`; only a masked preview (e.g. `sk-a...b3f2`) is ever sent back to the extension |
| Default provider/model preferences | `AppSettingsModel` (SQLite) | Which provider/model each task (scan/resume/field answer) uses |
| A few UI preferences | `chrome.storage.local` (in the browser, not the backend) | `baseResume` cache, `apiBaseUrl`, `onboardingComplete`, `extensionEnabled` — see `extension/src/shared/storage.ts` |

**Where the master key itself lives.** In the default Docker setup
(`make up`), `server/entrypoint.sh` auto-generates `MASTER_ENCRYPTION_KEY` on
first run and writes it to `/data/encryption.key` — inside the **same**
Docker volume as the database. That means the Fernet encryption on provider
keys mainly protects the database file in isolation (e.g. if it's copied out
on its own, or read from a backup); anyone with access to the whole `data`
volume has both the encrypted keys and the key to decrypt them. If you run
the backend manually instead (`cp .env.example .env` + `uvicorn`),
`MASTER_ENCRYPTION_KEY` lives wherever you put your own `.env` file — treat
it like any other secret, and never commit it.

None of this is sent to the maintainers of this project, uploaded to any
project-operated server, or used for analytics — because no such server
exists. There is no telemetry, crash reporting, or usage tracking anywhere
in the extension or backend code.

## The one thing that leaves your machine

When you click **Scan this page**, **Generate resume/cover letter**, or the
in-page **AI** button on a form field, the backend sends the minimum text
needed for that specific task (resume text, job text, and/or the target
field's context) to **the LLM provider you configured** — OpenAI, Google
Gemini, Anthropic Claude, or a local/remote **Ollama** endpoint — using
**your own API key** for cloud providers (Ollama needs no key for a local
daemon). Cloud requests go straight from your machine to the provider's
API over their official SDK; they do not pass through any server operated
by this project. With Ollama pointed at a local URL, that request stays on
your machine (or goes only to the host you set as `baseUrl`).

What the LLM provider does with the data it receives (retention, use in
model training, etc.) is governed by *that provider's* privacy policy and
terms of service, not by this project. Check the provider's own policy if
that matters to you — providers and their retention/training terms change
over time, so treat any specific claim as something to verify against the
current provider docs rather than something this project can promise on
your behalf.

## Chrome extension permissions

| Permission | Why |
|---|---|
| `sidePanel` | Renders the main UI |
| `activeTab`, `scripting`, `tabs` | Read the current page's content **only after** you click Scan, and detect/assist form fields **only after** you click the field's AI button |
| `storage` | Local `chrome.storage.local` preferences (see table above) |
| `downloads` | Saving generated `.docx` files to disk |
| `alarms` | Internal scheduling (e.g. periodic UI state checks) |
| Broad `host_permissions` (`http://*/*`, `https://*/*`) | The content script needs to be able to run on whatever job site or application-form page you're on, since job postings can be on any domain |

The content script is present on pages passively, but it **never reads or
sends page content without an explicit click** — no automatic scanning, no
automatic form filling, and no auto-submit of any form, ever. Sensitive
fields (password, payment, government ID, demographic) are explicitly
excluded from the AI-assist feature on both the extension side and the
backend side.

## Data retention & deletion

- Everything lives in the Docker volume for as long as you keep it. Nothing
  expires automatically.
- `make clean` (or `docker compose down -v`) **permanently deletes** the
  database and the encryption key. There is no recovery after this.
- Uninstalling or disabling the extension clears its `chrome.storage.local`
  preferences but does **not** touch the backend's Docker volume — stop/remove
  the backend separately if you want the resume/job data gone too.
- There is no cloud backup or sync of any kind — if you lose the Docker
  volume without a backup, the data is gone.

## Questions

Open a GitHub issue for general privacy questions about how the software
works. For a privacy-relevant *security* issue (e.g. a way data could leak
somewhere it shouldn't), please follow [SECURITY.md](SECURITY.md) instead of
filing a public issue.
