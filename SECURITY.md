# Security Policy

ResuMorph is a **local-first** tool: a Chrome extension paired with a backend
you run yourself (via Docker, on `localhost`). There is no hosted service
operated by this project and no server that receives your data. That said,
the project still handles sensitive material — resumes, job postings, LLM
provider API keys — and takes security reports seriously.

## Supported Versions

There are no long-term-support branches. Every merge to `main` is
automatically tagged and released (see `.github/workflows/auto-release.yml`),
so **only the latest release is supported**. If you report a vulnerability
against an older version, please confirm first whether it still reproduces
on the latest tag.

## Reporting a Vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

Preferred: use GitHub's private reporting flow —
**[Report a vulnerability](https://github.com/hannibalevit/resumorph/security/advisories/new)**
(repository **Security** tab → **Report a vulnerability**). This opens a
private advisory visible only to you and the maintainer.

Alternative: email **dev@hannibalevit.com** with a description of the
issue, steps to reproduce, and potential impact.

This is a solo-maintained open-source project, so there's no formal SLA —
expect a best-effort acknowledgement, typically within a few days.

**Coordinated disclosure.** Please don't disclose publicly until a fix is
out, or **90 days** from your initial report, whichever comes first — the
same window used across most of the industry. If a fix ships sooner, great;
if 90 days pass with no response or resolution, you're free to disclose. If
you need more time on your end before disclosing (or less), just say so in
the report — this is a default, not a rigid rule for a one-person project.

When reporting, please **do not** include your real resume text, job
descriptions, or live API keys in the report — describe the issue with
synthetic/redacted data where possible.

## Scope

Examples of what's in scope for a security report:

- **Secrets handling** — a way to read or exfiltrate a provider API key or
  `MASTER_ENCRYPTION_KEY` in plaintext, or a bypass of the Fernet encryption
  in [`server/app/security.py`](server/app/security.py) (only masked
  previews should ever reach the client — see `mask_secret`).
- **CORS / origin checks** — a way to make the backend accept requests from
  an origin it shouldn't (see the `CORSMiddleware` config and the
  `chrome-extension://` regex in [`server/app/main.py`](server/app/main.py)).
- **Sensitive form fields** — any way to get a password, payment, government
  ID, or demographic field sent to an LLM provider or the backend. This is
  meant to be blocked on *both* sides (extension detection and backend
  validation) — a bypass of either counts.
- **Prompt injection from scanned pages** — job posting text is untrusted
  input pulled from arbitrary third-party pages and fed into an LLM prompt.
  Reports showing this can be used to exfiltrate data across sessions,
  manipulate the backend beyond generating text, or escape the intended
  prompt in a dangerous way are welcome.
- **Injection / traversal** in generated-document handling
  ([`docx_generator.py`](server/app/docx_generator.py)), file uploads, or
  the SQLite layer.
- **Docker image issues** — privilege escalation, unnecessary root usage, or
  vulnerable base image dependencies.
- Anything that would cause data (resume text, job data, generated
  documents, or keys) to leave the user's machine other than the explicit,
  user-configured LLM API call.

## Known Design Tradeoffs (Not Vulnerabilities)

This project's threat model assumes a single trusted user running the
backend on their own machine. The following are intentional and are **not**
considered vulnerabilities on their own, though reports on how to make them
worse are still welcome:

- **The backend has no authentication.** Anything that can reach
  `http://localhost:8000` can read and write all local data, including the
  unauthenticated `/api/admin/*` endpoints that return full job sessions and
  generated artifacts. This is by design for a single-user local tool.
- **By default, the encryption key lives in the same Docker volume as the
  encrypted data it protects** — `entrypoint.sh` auto-generates
  `MASTER_ENCRYPTION_KEY` into `/data/encryption.key`, alongside the SQLite
  DB itself (see [PRIVACY.md](PRIVACY.md) for the full explanation). Fernet
  encryption here protects the DB file *in isolation* (e.g. copied out on
  its own, or restored from a backup) — not against anyone who already has
  access to the whole `data` volume, since the key sits right there too.
  Reports proposing a better default (e.g. an option to keep the key outside
  the volume) are welcome; reports that just point out the co-location
  itself aren't new information — it's documented, intentional, and follows
  from the "single trusted local user" threat model above.
- **`docker-compose.yml` binds port 8000 to `127.0.0.1` only by default** —
  not reachable from other devices on your network. If you deliberately want
  LAN access (e.g. running the backend on a machine separate from the
  browser), override the `ports` mapping in your own compose file; doing so
  removes this protection, since the API itself has no authentication (see
  above), so treat that network as trusted before opening it up.
- **`ALLOWED_ORIGINS` defaults to `http://localhost:5173`** (matching
  `app/config.py`'s own default), not `*`. The extension's
  `chrome-extension://<id>` origin is allowed independently via a separate
  regex in `CORSMiddleware`, so this setting only matters for
  browser-based dev workflows (e.g. the side panel's Vite dev server) —
  widening it is a deliberate opt-in, not something the extension needs.
- **Vulnerabilities in third-party LLM providers** (OpenAI, Google Gemini,
  Anthropic) themselves are out of scope here — please report those to the
  respective vendor.
- Attacks that require the attacker to already have arbitrary code
  execution on the user's machine (at which point the local SQLite DB and
  encryption key are moot) are out of scope.

## Dependencies

Runtime dependencies are pinned (`server/uv.lock`,
`extension/package-lock.json`) and the backend is built from a specific
Python base image (see `server/Dockerfile`). If you find a known-vulnerable
pinned version, a report or PR bumping it (with `uv add`/`npm install` so the
lockfile updates too) is welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

## Acknowledgments

With permission, this section will credit anyone who responsibly reports a
valid vulnerability, once a fix has shipped. Nobody's reported one yet —
you could be the first.

## See Also

- [PRIVACY.md](PRIVACY.md) — what data the extension/backend collect and
  where it goes.
- [CLAUDE.md](CLAUDE.md) / [AGENTS.md](AGENTS.md) — detailed data-handling
  and privacy-preserving conventions enforced in code review.
