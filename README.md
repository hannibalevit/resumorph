# 📄 Resume Tailor

[![Release](.github/badges/version.svg)](https://github.com/hannibalevit/resume-tailor/releases)
[![Backend coverage](.github/badges/coverage.svg)](.github/workflows/server-ci.yml)

> A Chrome Side Panel extension that tailors your resume to any job posting — privately, locally, on your machine.

Paste your base resume once. Open any job page, click **Scan this page**, and get a tailored `.docx` resume or cover letter in seconds. All data stays on your machine; only the LLM API call leaves it.

---

## Table of Contents

- [How it works](#how-it-works)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
  - [Step 1 — Start the backend](#step-1--start-the-backend)
  - [Step 2 — Load the extension in Chrome](#step-2--load-the-extension-in-chrome)
  - [Step 3 — Configure an LLM provider](#step-3--configure-an-llm-provider)
- [Using the extension](#using-the-extension)
- [Useful commands](#useful-commands)
- [Rebuilding the extension from source](#rebuilding-the-extension-from-source)
- [Project structure](#project-structure)
- [Troubleshooting](#troubleshooting)

---

## How it works

```
Job page  ──[Scan]──▶  Chrome Extension  ──[POST]──▶  Local FastAPI server
                                                              │
                                                    ┌─────────┴─────────┐
                                                    │  SQLite database  │
                                                    │  (your data only) │
                                                    └─────────┬─────────┘
                                                              │
                                                    ┌─────────▼─────────┐
                                                    │   LLM API call    │
                                                    │  (OpenAI/Gemini/  │
                                                    │   Claude)         │
                                                    └───────────────────┘
                                                              │
                              ◀──────[.docx resume / cover letter]──────┘
```

The extension never reads your pages automatically — it only scans after you click **Scan this page**. Form fields are only assisted when you click the **AI** button on that specific field.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | macOS, Windows, or Linux |
| Google Chrome | or any Chromium-based browser (Edge, Arc, Brave) |
| An LLM API key | OpenAI, Google Gemini, or Anthropic Claude — any one is enough |

---

## Quick Start

### Step 1 — Start the backend

```bash
git clone <repo-url>
cd resume-tailor-extension
make up
```

<details>
<summary>Don't have <code>make</code>? Use Docker directly</summary>

```bash
docker compose up -d --build
```

</details>

On first run, Docker will automatically:

- ✅ Build the Python image and install all dependencies
- ✅ Generate a secure encryption key (`MASTER_ENCRYPTION_KEY`) and store it in a persistent volume
- ✅ Create the SQLite database (your data survives container restarts and updates)
- ✅ Expose the API at **http://localhost:8000**

Verify the server is ready:

```bash
curl http://localhost:8000/health
# → {"status":"ok"}
```

> 💡 **You don't need to set an API key now.** You'll enter it in the extension's Settings panel after loading it in Chrome.

---

### Step 2 — Load the extension in Chrome

The pre-built extension is included in `extension/dist/` — no Node.js required.

1. Open **`chrome://extensions`** in Chrome
2. Enable **Developer mode** (toggle in the top-right corner)
3. Click **Load unpacked**
4. Select the **`extension/dist`** folder from this repository

The 📄 Resume Tailor icon will appear in your Chrome toolbar. Click it to open the Side Panel.

---

### Step 3 — Configure an LLM provider

Open the Side Panel → click **Settings** → enter an API key:

| Provider | Recommended model | Get a key |
|---|---|---|
| **OpenAI** | `gpt-4.1-mini` | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| **Google Gemini** | `gemini-2.5-flash-lite` | [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) |
| **Anthropic Claude** | `claude-3-5-haiku-latest` | [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys) |

Click **Test connection** → **Set as Default**. The key is encrypted and stored in your local database — it never leaves your machine in plaintext.

> ⚠️ Without a key, the extension uses a basic local fallback that is much less accurate.

---

## Using the extension

1. **Upload your resume** — open the Side Panel and upload a `.pdf`, `.docx`, `.txt`, or `.md` file
2. **Navigate to a job posting** — LinkedIn, Greenhouse, Lever, Indeed, or any page
3. **Scan the page** — click **Scan this page**; a job tab appears with extracted requirements and keywords
4. **Generate documents** — click **Generate resume** or **Generate cover letter** and save the `.docx`
5. **Fill forms faster** — on application forms, non-sensitive text fields get an **AI** button; click it to preview a draft, then **Insert**, **Copy**, or **Cancel**

> 🔒 The extension never auto-submits forms, clicks Apply/Next, or touches password, payment, ID, or demographic fields.

---

## Useful commands

| Command | Description |
|---|---|
| `make up` | Build image and start the server in the background |
| `make down` | Stop the server |
| `make restart` | Restart the server |
| `make logs` | Stream live server logs |
| `make build-extension` | Rebuild extension from source (requires Node.js 18+) |
| `make clean` | ⚠️ Stop server and permanently delete all local data |

---

## Rebuilding the extension from source

Only needed if you modify the extension code:

```bash
make build-extension
```

Then reload the extension: go to `chrome://extensions` and click the **↺** reload icon next to Resume Tailor.

---

## Project structure

```
resume-tailor-extension/
├── extension/
│   ├── dist/               ← pre-built extension — load this in Chrome
│   └── src/
│       ├── background/     ← service worker, side-panel activation
│       ├── content/        ← page scanner, form detector, inline AI button
│       └── sidepanel/      ← React UI
├── server/
│   ├── app/                ← FastAPI application
│   │   ├── main.py
│   │   ├── models.py
│   │   ├── security.py
│   │   └── ...
│   ├── Dockerfile
│   ├── entrypoint.sh       ← auto-generates encryption key on first run
│   ├── pyproject.toml      ← dependencies (managed with uv)
│   └── uv.lock
├── docker-compose.yml
├── Makefile
└── README.md
```

---

## Troubleshooting

**Extension shows "Server offline"**

```bash
curl http://localhost:8000/health
make logs
```

Make sure Docker Desktop is running and the container started without errors.

---

**"Load unpacked" button is greyed out**

Enable **Developer mode** in `chrome://extensions` first (toggle in the top-right corner).

---

**After a Chrome update, the extension is disabled**

Chrome sometimes disables unpacked extensions after updates. Go to `chrome://extensions` and click **Enable** next to Resume Tailor.

---

**Job scan returns generic or inaccurate results**

Check that you have a working LLM provider set as Default in **Settings**. Without a configured key, the extension falls back to a basic local extractor.

---

**I want to reset everything and start fresh**

```bash
make clean
```

This stops the server and deletes the Docker volume (database + encryption key). The next `make up` starts completely fresh.

---

<div align="center">
  <sub>Built for local, private use — your resume data stays on your machine.</sub>
</div>
