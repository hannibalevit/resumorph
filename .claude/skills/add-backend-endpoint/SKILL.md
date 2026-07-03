---
name: add-backend-endpoint
description: Use when adding a new FastAPI route/endpoint under server/app/routers/, or a new router module. Covers the wiring, camelCase contract, and test-stubbing conventions that are easy to get wrong or forget.
---

# Add a backend endpoint

## Steps

1. Add the handler to the router module matching its resource
   (`routers/{health,settings,profile,job_sessions,artifacts,admin,legacy}.py`),
   or create a new module with `router = APIRouter()` (no prefix — write the
   full `/api/...` path on each route decorator, matching existing style).
2. If it's a new module, import it in `server/app/main.py` and add it to the
   `include_router` loop tuple — a router that isn't registered there is dead
   code with no error to flag it.
3. Handler must be `async def` (all 32 existing route handlers are async —
   this is a hard convention here, not a suggestion).
4. Inject the DB session via `db: Session = Depends(get_db)`.
5. Define request/response shapes in `schemas.py` using `ApiModel` (sets
   `populate_by_name=True`) with `Field(alias="camelCase")` on every field —
   the wire format is camelCase, Python stays snake_case. Set
   `response_model=` on the route decorator.
6. Map SQLAlchemy models to response schemas via a function in
   `serializers.py`, not inline in the router.
7. Raise errors with `raise fail(status_code, "SOME_CODE", "message", **details)`
   from `errors.py` — never raise a bare `HTTPException` or return an ad-hoc
   error shape.
8. If the endpoint calls an LLM, do the orchestration in
   `services/generation.py` (the router should call into a service function,
   not call `get_llm_provider`/`resolve_task_llm` directly).
9. Add the corresponding `api.*` entry in `extension/src/shared/apiClient.ts`
   if the extension will call it — don't let UI code do ad-hoc `fetch`.

## Tests

Add tests to `server/tests/test_api_endpoints.py` using the existing fixtures:
- `client` — `TestClient` with `get_db` overridden to the test session.
- `db_session` — in-memory SQLite, fresh per test.
- `stub_llm` — if the endpoint hits an LLM, this fixture patches
  `resolve_task_llm` and `get_llm_provider` **on `app.services.generation`**
  (not on the provider module or the router module) — that's the name the
  service layer imports, so that's the name to patch.
- Assert error responses via `response.json()["error"]["code"]`, matching the
  `fail()` envelope shape.

## Verify

From `server/`: `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run deptry . && uv run pytest`.
Coverage must stay ≥85% (`--cov-fail-under=85`) — a new endpoint with no test
can drop the whole suite below the gate even if the endpoint itself is
correct. None of this runs in CI (only `extension/` has a workflow), so this
local run is the only check that will ever catch a regression here.

## Gotchas

- Forgetting the `include_router` wiring in `main.py` is the most common way
  a new endpoint silently 404s with no test failure to explain why (unless a
  test hits it directly).
- Skipping the `Field(alias="camelCase")` on a new schema field breaks the
  wire contract with the extension without any backend-side error — the field
  will just serialize as snake_case and the TS client won't find it.
