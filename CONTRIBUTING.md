# Contributing to ResuMorph

Thanks for considering a contribution. This repo contains two independent
projects that happen to ship together:

- `extension/` — a TypeScript Chrome MV3 extension (Vite + React + Vitest)
- `server/` — a Python FastAPI backend (SQLAlchemy + SQLite, managed with
  [uv](https://docs.astral.sh/uv/))

Please read [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) — participation in this
project means agreeing to abide by it.

If you find a security vulnerability, **do not** open a public issue — see
[SECURITY.md](SECURITY.md) instead.

## Ways to contribute

- **Bug reports** and **feature requests** via GitHub Issues (templates are
  provided and will guide you).
- **Pull requests** — fixes, new job-site extractors, new LLM providers/
  tasks, docs improvements, test coverage.
- **Documentation** — the README, this file, and the docs in `server/` and
  `extension/` are all fair game.

For anything larger than a small fix (a new LLM provider, a new DB column, a
new endpoint), please open an issue first to discuss the approach before
investing time in a PR.

## Getting the code

Unless you already have write access to this repository, contribute through
a **fork**. That's the normal path here, not a second-class one — write
access is deliberately limited to a small number of maintainers, because it
also grants access to CI secrets and to the release artifacts users install.

Fork the repo from its
[GitHub page](https://github.com/hannibalevit/resumorph), then:

```bash
git clone https://github.com/<your-username>/resumorph.git
cd resumorph
git remote add upstream https://github.com/hannibalevit/resumorph.git

git fetch upstream
git switch -c feat/my-change upstream/main
# ...work, commit...
git push -u origin feat/my-change
```

Then open the PR from that branch against this repo's `main`.

A few things worth knowing:

- **Work on a branch, not your fork's `main`.** Committing straight to
  `main` means you can only ever have one PR open, and updating it after
  review gets messy.
- **Leave "Allow edits by maintainers" checked** (it's on by default) so a
  maintainer can push a small fix to your branch rather than sending you
  through another review round-trip.
- **`main` requires branches to be up to date before merging**, so you may
  be asked to rebase:
  `git fetch upstream && git rebase upstream/main && git push --force-with-lease`.

### What CI looks like on a fork PR

`server-ci.yml` and `extension-ci.yml` both run on `pull_request`, so all
five required status checks report on your PR exactly as they would on an
in-repo branch. Two things differ, and both are intentional:

- **Workflows wait for a maintainer to click "Approve and run"** — on every
  push to your PR, not just the first one. Nothing is wrong with your PR;
  this repo requires approval for all external contributors so that someone
  reads the diff before unreviewed code runs on the project's runners with
  access to its CI. Expect a short delay before checks start moving.
- **Fork runs get a read-only token and no repository secrets.** Every
  required check works without them; the one job that does need a secret
  (the coverage badge) only runs after merge, so it can't fail on your PR.

## Development setup

### Backend (`server/`)

```bash
cd server
uv sync --dev
cp .env.example .env   # set MASTER_ENCRYPTION_KEY (a Fernet key) and at least one LLM key
uv run uvicorn app.main:app --reload --port 8000
curl http://localhost:8000/health
```

### Extension (`extension/`)

```bash
cd extension
npm install
npm run dev      # Vite dev mode
npm run build     # tsc --noEmit && vite build -> extension/dist/
```

Load `extension/dist` as an unpacked extension via `chrome://extensions`
(enable Developer mode first), and reload it after every rebuild.

### Or just run everything in Docker

```bash
make up      # build + start the backend on :8000
make logs
make down
```

See the [README](README.md) for the full quick-start walkthrough.

## Before opening a PR

Run the checks for whatever you touched. These are exactly what CI runs
(`.github/workflows/server-ci.yml`, `.github/workflows/extension-ci.yml`),
so a clean local run means CI should pass too.

**Backend** (from `server/`):

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run deptry .
uv run pytest
```

Backend coverage must stay at or above **85%** (`--cov-fail-under=85` in
`pytest.ini`) — add tests for new/changed behavior rather than letting the
gate slide.

**Extension** (from `extension/`):

```bash
npm test
npm run build
```

`npm run build` runs `tsc --noEmit` in strict mode with `noUnusedLocals`/
`noUnusedParameters` enabled, so unused symbols and type errors fail the
build, not just lint.

## Code conventions

The canonical, detailed description of this codebase's architecture and
conventions lives in [CLAUDE.md](CLAUDE.md) (and its condensed counterpart,
[AGENTS.md](AGENTS.md)) — please skim the relevant sections before a
non-trivial change. A few of the most consequential rules, since getting
them wrong tends to fail review or CI in non-obvious ways:

- **Wire format**: Python/SQLAlchemy stays snake_case; JSON over the wire is
  camelCase via Pydantic `by_alias=True`. TS types in `apiClient.ts` /
  `sidepanelTypes.ts` mirror the camelCase shape.
- **No Alembic** — if you add a column to a model in `server/app/models.py`,
  you must also add it to the `MIGRATIONS` dict in `server/app/db_migrations.py`,
  or existing local databases won't pick it up. Migrations are additive only
  (`ALTER TABLE ADD COLUMN`); renames/drops need a separate explicit plan.
- **LLM calls are centralized** in `server/app/services/generation.py` — new
  generation logic belongs there, not in routers or provider classes, and
  tests stub the LLM by patching names imported by that module.
- **New provider/task pairs need prompts for every provider** —
  `server/app/prompts/<provider>/<task>.{system,user}.md` must exist for
  every provider, or `render_prompt` raises `FileNotFoundError` at request
  time (not at startup).
- **Sensitive form fields** (password, payment, government ID, demographic)
  must stay excluded from AI assistance on *both* the extension side
  (`content/formDetector.ts`) and the backend side (`generate_field_answer`)
  — don't remove one check without removing the other.
- **No ad-hoc `fetch` calls** in the extension — add new backend calls to
  `extension/src/shared/apiClient.ts`, and never hardcode the backend base
  URL; use `getApiBaseUrl()`.
- **New job sites**: add an extractor under
  `extension/src/content/jobExtraction/siteExtractors/` and register it in
  that folder's `index.ts`.
- Don't loosen CORS or Chrome extension permissions without explaining why
  the feature genuinely needs it — see [SECURITY.md](SECURITY.md) for the
  current threat model.

## Using Claude Code (and other AI coding agents) in this repo

None of this is required to contribute — everything above stands on its own.
But this repo ships checked-in configuration for AI coding agents, on the
theory that the same conventions that keep a human reviewer sane also keep
an agent from making the same predictable mistakes. If you use Claude Code
or a similar tool, here's what's here and what it does.

**Instruction files** — `CLAUDE.md` (repo root) is the canonical, detailed
architecture/conventions doc; Claude Code loads it automatically for any
session started in this repo. `AGENTS.md` (repo root) is a condensed version
of the same conventions, written for Codex and other agents that follow the
`AGENTS.md` convention instead. Keep both in sync when a convention changes —
a PR that updates one and not the other is easy to miss in review.

**Claude Code skills** (`.claude/skills/`) — four skills wired into Claude
Code's `Skill` tool, invocable by name (`/add-backend-endpoint`, etc.) or
picked up automatically when a task matches their description:

- `add-backend-endpoint` — wiring a new FastAPI route: router registration,
  camelCase schema fields, serializer, test-stubbing conventions.
- `add-db-column` — adding a SQLAlchemy model column plus the matching entry
  in the hand-rolled `db_migrations.py` (there's no Alembic).
- `add-llm-task-or-provider` — adding a generation task or LLM provider,
  including the "every provider needs every prompt file" trap.
- `commit` — commits changes with a Conventional Commits message matching
  the `pr-title-lint.yml` / `cliff.toml` rules below.

**Broader agent skills** (`.agents/skills/`) — a second set of six skill
files (`backend-api-change`, `chrome-extension-review`, `database-migration`,
`llm-prompt-change`, `privacy-security-review`, `release-testing-checklist`)
in the same skill-file format, but not wired into Claude Code's `Skill` tool
in this repo — they're tool-agnostic workflow/validation/failure-mode
checklists, and overlap in places with the three `.claude/skills/` above
(e.g. `backend-api-change` and `database-migration` cover similar ground to
`add-backend-endpoint` and `add-db-column`, as a leaner checklist rather
than a narrative walkthrough). Worth reading regardless of which agent (or
none) you're using — `chrome-extension-review`, `privacy-security-review`,
and `release-testing-checklist` in particular have no `.claude/skills/`
equivalent yet.

**Custom subagent** (`.claude/agents/backend-verifier.md`) — runs the full
backend preflight (`ruff check`, `ruff format --check`, `mypy`, `deptry`,
`pytest` with coverage) from `server/` and reports back a compact pass/fail
summary instead of raw tool output. `.github/workflows/server-ci.yml` runs
this same gate in CI on every PR, but that's minutes away and after the fact
(longer still on a fork PR, which waits for a maintainer to approve the run)
— this subagent is what actually catches a regression before you push, with
CI as the backstop.

**Hooks** (`.claude/hooks/`, wired via `.claude/settings.json`) — run
automatically for anyone using Claude Code in this repo:

- `guard-bash.sh` (`PreToolUse` on `Bash`) blocks any `git add`/`git commit`
  referencing `server/.env` or an `encryption.key` file, and blocks
  `make clean` / `docker compose down -v` (both permanently delete the local
  database and encryption key).
- `format-python.sh` (`PostToolUse` on `Edit`/`Write`) runs `ruff format` on
  any touched `server/**/*.py` file automatically, since nothing else
  enforces formatting turn-by-turn.

These are safety/convenience nets for agent-driven edits, not a substitute
for the manual checks in [Before opening a PR](#before-opening-a-pr) above.

**Codex config** (`.codex/config.toml`) — minimal, no MCP servers
configured. Keep it that way unless a verified, documented integration is
actually needed.

## Commit style & branching

PR titles must follow [Conventional Commits](https://www.conventionalcommits.org/)
(`feat:`, `fix:`, `perf:`, `refactor:`, `docs:`, `chore:`, `ci:`, `test:` —
optionally scoped, e.g. `feat(sidepanel):`, with a `!` for breaking changes,
e.g. `feat!:`). This is enforced by CI
(`.github/workflows/pr-title-lint.yml`, via
[amannn/action-semantic-pull-request](https://github.com/amannn/action-semantic-pull-request))
on every PR title, running alongside `server-ci.yml` / `extension-ci.yml`,
not in place of them. PRs are squash-merged, so the PR title becomes the
commit message on `main` — this isn't just a style rule, that commit message
is what directly drives both the changelog and the version bump on release.

Important: **every push to `main` is automatically released**
(`.github/workflows/auto-release.yml` + `cliff.toml`, via
[git-cliff](https://git-cliff.org/)):

- The next version is derived from Conventional Commits since the last `v*`
  tag: a `feat:` bumps minor, a `fix:` (or any other non-breaking
  conventional type) bumps patch, and a breaking change (`!` after the type
  or a `BREAKING CHANGE:` footer) bumps major.
- If there are no conventional commits since the last tag (e.g. only
  `chore:`/`ci:`/`docs:`), no release is cut.
- A categorized changelog entry is generated and prepended to
  `CHANGELOG.md`, and reused as the GitHub Release body.

Because of this:

- Don't hand-edit version fields (`extension/manifest.json`'s `version`,
  `server/pyproject.toml`'s `version`) — the release workflow owns them.
- Don't hand-edit `CHANGELOG.md` — it's generated by `git-cliff` from commit
  history on every release, same rule as `extension/dist/` below.
- Don't hand-edit `extension/dist/` — it's committed as a build artifact and
  the release workflow regenerates it from source on every release. Change
  `extension/src/` instead.
- Open PRs against `main` from a feature branch — in your fork, unless you
  have write access here (see [Getting the code](#getting-the-code)). Once
  merged, a release happens automatically whenever there's a releasable
  change; there's no separate manual publish step.

## License

By contributing, you agree that your contributions will be licensed under
the [Apache License 2.0](LICENSE), the same license as the rest of the
project (per section 5 of that license — no separate CLA is required).

## Getting help

Open a GitHub issue if you're stuck or unsure whether an approach fits the
project's direction — that's cheaper for everyone than a large PR that goes
in an unexpected direction.
