---
name: release-testing-checklist
description: Use before finishing broad or release-like changes, or when asked to verify the repository end to end.
---

# Release Testing Checklist

## Workflow

1. Inspect `git status --short` and identify backend, extension, docs, and generated-output changes.
2. For backend changes, run all backend checks from `server/`.
3. For extension changes, run `npm test` and `npm run build` from `extension/`.
4. For Docker/runtime changes, run `make up`, check `curl http://localhost:8000/health`, inspect `make logs` as needed, then stop with `make down` unless the user wants it left running.
5. For privacy-sensitive changes, apply the `privacy-security-review` skill.
6. Confirm generated or local-only artifacts are not accidentally included.
7. Summarize pass/fail status concisely.

## Validation

Backend:

```bash
cd server
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run deptry .
uv run pytest
```

Extension:

```bash
cd extension
npm test
npm run build
```

Runtime:

```bash
make up
curl http://localhost:8000/health
make down
```

Do not run `make clean` for release validation.

## Common Failure Modes

- Backend checks are skipped because extension CI exists, even though backend CI may not catch regressions.
- Coverage fails the 85% gate although tests pass.
- `extension/dist/` changes are mistaken for source changes.
- Docker data is wiped during validation.
- Validation output is too noisy to act on.

## Expected Output

Report each check as pass, fail, or not run. For failures, include the specific command and actionable error summary, not a full log dump.
