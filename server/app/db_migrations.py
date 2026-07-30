"""Hand-rolled additive schema migrations.

There is no Alembic. On startup we create any missing tables and then diff each
table's current columns against the hardcoded ``MIGRATIONS`` dict below, running
``ALTER TABLE ADD COLUMN`` for anything missing. When you add a column to a model,
add it here too or existing SQLite DBs won't pick it up.
"""

from sqlalchemy import Engine, inspect, text

from app.database import Base

MIGRATIONS: dict[str, dict[str, str]] = {
    "job_sessions": {
        "llm_provider_used": "VARCHAR(32)",
        "llm_model_used": "VARCHAR(255)",
        "scan_llm_provider": "VARCHAR(32)",
        "scan_llm_model": "VARCHAR(255)",
        "resume_generation_provider": "VARCHAR(32)",
        "resume_generation_model": "VARCHAR(255)",
        "cover_letter_generation_provider": "VARCHAR(32)",
        "cover_letter_generation_model": "VARCHAR(255)",
    },
    "llm_provider_configs": {
        "available_models": "JSON",
        "models_updated_at": "DATETIME",
        "base_url": "VARCHAR(512)",
    },
    "generated_artifacts": {
        "llm_provider": "VARCHAR(32)",
        "llm_model": "VARCHAR(255)",
        "prompt_version": "VARCHAR(64)",
        "generation_metadata_json": "JSON",
    },
    "app_settings": {
        "scan_provider": "VARCHAR(32)",
        "scan_model": "VARCHAR(255)",
        "resume_provider": "VARCHAR(32)",
        "resume_model": "VARCHAR(255)",
        "field_answer_provider": "VARCHAR(32)",
        "field_answer_model": "VARCHAR(255)",
    },
}


def run_migrations(engine: Engine) -> None:
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    with engine.begin() as connection:
        for table, columns in MIGRATIONS.items():
            existing = {item["name"] for item in inspector.get_columns(table)}
            for column, definition in columns.items():
                if column not in existing:
                    connection.execute(
                        text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
                    )
