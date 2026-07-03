---
name: add-db-column
description: Use when adding a new column/field to a SQLAlchemy model in server/app/models.py (e.g. "add a field to JobSession", "store X on the user profile"). There is no Alembic — a model-only change silently breaks existing SQLite DBs.
---

# Add a DB column

This project has no Alembic. Migrations are a hand-rolled additive diff in
`server/app/db_migrations.py`, run from the FastAPI `lifespan` startup hook.
A column that exists only on the SQLAlchemy model but not in the `MIGRATIONS`
dict will work on a fresh DB (via `Base.metadata.create_all`) but silently
fail to appear on any existing SQLite DB — no error, just a missing column
that surfaces as a runtime `OperationalError` later.

## Steps

1. Add the `mapped_column(...)` to the relevant model class in
   `server/app/models.py` (`Mapped[...]` / `mapped_column(...)` style, matching
   the surrounding fields).
2. In `server/app/db_migrations.py`, find the `MIGRATIONS` dict entry for that
   table and add `"column_name": "SQL_TYPE"` — the SQL type string, not the
   Python type (e.g. `"TEXT"`, `"INTEGER"`, `"BOOLEAN"`).
3. If the column feeds the API, update the matching Pydantic schema in
   `server/app/schemas.py` (remember `Field(alias="camelCase")`) and the
   mapper in `server/app/serializers.py`.
4. If it's part of a request/response the extension consumes, update the
   corresponding TS type in `extension/src/shared/apiClient.ts` or
   `sidepanelTypes.ts`.
5. Verify: `uv run pytest` (from `server/`) exercises the migration path via
   the in-memory test DB in `conftest.py`; also sanity-check against a real
   on-disk SQLite file if the change is non-trivial (delete-safe: use a throwaway
   `DATABASE_URL`, don't touch the real `/data` volume or `server/.env` DB).

## Gotchas

- Only additive `ALTER TABLE ADD COLUMN` is supported — no renames, drops, or
  type changes via this mechanism. A breaking schema change needs a manual
  one-off script, not this flow.
- The `MIGRATIONS` dict key must match the table name exactly (as defined by
  `__tablename__` on the model), not the model class name.
