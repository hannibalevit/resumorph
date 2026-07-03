---
name: database-migration
description: Use when adding a SQLAlchemy model column or changing persisted SQLite data shape in the FastAPI backend.
---

# Database Migration

## Workflow

1. Find the model in `server/app/models.py` and confirm the table name from `__tablename__`.
2. Add the `Mapped[...]` field and `mapped_column(...)` using the surrounding style.
3. Add the same column to the matching table entry in `server/app/db_migrations.py::MIGRATIONS`.
4. Use SQLite SQL type strings in `MIGRATIONS`, such as `TEXT`, `INTEGER`, or `BOOLEAN`.
5. If the field is API-visible, update `server/app/schemas.py` and `server/app/serializers.py`.
6. If the extension consumes the field, update TypeScript types in `extension/src/shared/apiClient.ts` or `extension/src/shared/sidepanelTypes.ts`.
7. Add or update tests that cover fresh DB creation and migration behavior where practical.

## Validation

Run from `server/`:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run deptry .
uv run pytest
```

For non-trivial persistence work, use a throwaway SQLite database for manual startup checks. Do not touch the real Docker data volume.

## Common Failure Modes

- Model column is added but `MIGRATIONS` is not updated, breaking existing SQLite databases.
- The migration table key does not match `__tablename__`.
- A non-additive change is attempted through the additive migration mechanism.
- API schemas or TypeScript types are left out of sync with persisted data.
- Tests pass only against fresh metadata creation and do not exercise migration assumptions.

## Expected Output

Report the model field, migration entry, any API/type updates, tests added or changed, and validation results.
