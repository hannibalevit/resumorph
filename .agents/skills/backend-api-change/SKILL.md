---
name: backend-api-change
description: Use when adding or changing FastAPI routes, request/response schemas, serializers, or backend API behavior consumed by the extension.
---

# Backend API Change

## Workflow

1. Identify the resource owner under `server/app/routers/`.
2. Add or edit the route in the matching router module. For a new router, define `router = APIRouter()`, use full `/api/...` paths on decorators, import it in `server/app/main.py`, and add it to the `include_router` loop.
3. Keep route handlers `async def`.
4. Inject database sessions with `db: Session = Depends(get_db)`.
5. Define API shapes in `server/app/schemas.py` using `ApiModel` and `Field(alias="camelCase")` for wire fields.
6. Map SQLAlchemy models to response schemas in `server/app/serializers.py`.
7. Raise errors with `raise fail(status_code, "CODE", "message", **details)`.
8. If the route invokes an LLM, put orchestration in `server/app/services/generation.py`.
9. If the extension consumes the endpoint, add or update the corresponding `api.*` method and types in `extension/src/shared/apiClient.ts`.
10. Add focused tests in `server/tests/test_api_endpoints.py` or the closest existing test file.

## Validation

Run from `server/`:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run deptry .
uv run pytest
```

If extension API types changed, also run from `extension/`:

```bash
npm test
npm run build
```

## Common Failure Modes

- New router is not registered in `main.py`.
- A schema field serializes as snake_case because `Field(alias="camelCase")` was omitted.
- Router returns a SQLAlchemy model directly instead of using a serializer.
- LLM code is placed in a router, making tests harder to stub.
- Tests patch provider modules instead of names imported by `app.services.generation`.
- Extension UI uses an ad-hoc `fetch` instead of `apiClient.ts`.

## Expected Output

Report changed route files, schema/serializer updates, extension client updates, tests added or changed, and validation results.
