## Summary

<!-- What does this PR change, and why? -->

## Area(s) changed

- [ ] Extension (`extension/`)
- [ ] Backend (`server/`)
- [ ] Docker / infra (`docker-compose.yml`, `Dockerfile`, `Makefile`, workflows)
- [ ] Documentation only

## Checklist

Only check the boxes that apply to this PR's area(s) changed.

**Backend** (from `server/`):

- [ ] `uv run ruff check .` passes
- [ ] `uv run ruff format --check .` passes
- [ ] `uv run mypy` passes
- [ ] `uv run deptry .` passes
- [ ] `uv run pytest` passes, coverage stayed ≥ 85%
- [ ] Added a model column? → also added it to `MIGRATIONS` in `server/app/db_migrations.py`
- [ ] Added an LLM task/provider or edited a prompt? → `.system.md`/`.user.md` present for **every** provider under `server/app/prompts/`
- [ ] Touched `generate_field_answer` or field-sensitivity logic? → sensitive fields (password/payment/ID/demographic) are still rejected server-side

**Extension** (from `extension/`):

- [ ] `npm test` passes
- [ ] `npm run build` passes (includes `tsc --noEmit` in strict mode)
- [ ] New backend call added to `extension/src/shared/apiClient.ts` (no ad-hoc `fetch`)
- [ ] New job-site extractor registered in `siteExtractors/index.ts`
- [ ] Touched form detection? → sensitive fields (password/payment/ID/demographic) are still excluded client-side
- [ ] Did **not** hand-edit `extension/dist/` (it's a generated build artifact)

**Docker / infra** (`docker-compose.yml`, `Dockerfile`, `Makefile`, `.github/workflows/`):

- [ ] `make up` (or `docker compose up -d --build`) builds and serves cleanly from a clean state
- [ ] `curl http://localhost:8000/health` succeeds against the rebuilt container
- [ ] Changed a workflow file? → ran/dry-ran it (e.g. on a fork or a draft PR) rather than only reading the YAML
- [ ] Changed `Dockerfile`/`entrypoint.sh`? → still consistent with the `docker-image-smoke-test` job in `server-ci.yml`

**Cross-cutting**

- [ ] No secrets, `.env` contents, real resumes/job text, or API keys included in the diff, tests, or fixtures
- [ ] No unrelated version bumps (`extension/manifest.json` / `server/pyproject.toml` versions are owned by the release workflow)
- [ ] CORS / Chrome permissions unchanged, or the reason a broader scope is genuinely needed is explained below — see [SECURITY.md](../SECURITY.md)'s threat model before loosening either
- [ ] New dependency added? → license is compatible with [Apache-2.0](../LICENSE), and it's added via `uv add`/`npm install` (not hand-edited) so the lockfile matches
- [ ] Checked [CLAUDE.md](../CLAUDE.md) / [AGENTS.md](../AGENTS.md) for conventions relevant to the area(s) you touched

## Related issue(s)

<!-- e.g. "Closes #123" if this PR fully resolves the issue, or "Relates to #123" if it's partial/related work -->

## Notes for reviewers

<!-- Anything a reviewer should know: assumptions, follow-ups, things you're unsure about. -->
