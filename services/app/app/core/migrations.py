from pathlib import Path

from sqlalchemy import text

from app.core.database import get_engine


# Resolve from the application package so the same code works in Docker
# (/workspace/migrations) and from a local source checkout
# (services/app/migrations).
MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


def bootstrap_database(connection) -> None:
    """Create the minimum database contract required by the migration runner.

    Offline Docker users may only receive the three images and a Compose file,
    so startup must not depend on a host-mounted ``docker-entrypoint-initdb.d``
    directory. All statements are idempotent and are also safe when the legacy
    PostgreSQL init script has already run.
    """
    for statement in (
        "CREATE EXTENSION IF NOT EXISTS vector",
        "CREATE EXTENSION IF NOT EXISTS pg_trgm",
        "CREATE SCHEMA IF NOT EXISTS app",
        "CREATE SCHEMA IF NOT EXISTS demo",
        (
            "CREATE TABLE IF NOT EXISTS app.app_config ("
            "config_key TEXT PRIMARY KEY, "
            "config_value JSONB NOT NULL, "
            "updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())"
        ),
        (
            "INSERT INTO app.app_config (config_key, config_value) VALUES "
            "('project_stage', '\"phase-0\"'::jsonb), "
            "('dataset_max_business_date', 'null'::jsonb) "
            "ON CONFLICT (config_key) DO NOTHING"
        ),
        (
            "CREATE TABLE IF NOT EXISTS app.schema_migration ("
            "filename TEXT PRIMARY KEY, "
            "applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW())"
        ),
    ):
        connection.exec_driver_sql(statement)


def run_migrations() -> None:
    if not MIGRATIONS_DIR.is_dir():
        return

    engine = get_engine()
    with engine.begin() as connection:
        bootstrap_database(connection)

    for migration_path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        with engine.begin() as connection:
            applied = connection.execute(
                text("SELECT 1 FROM app.schema_migration WHERE filename = :filename"),
                {"filename": migration_path.name},
            ).scalar_one_or_none()
            if applied:
                continue

            # psycopg uses percent-style parameter parsing even when the SQL file
            # has no bound parameters. Escape SQL modulo operators and '%' units.
            sql = migration_path.read_text(encoding="utf-8").replace("%", "%%")
            connection.exec_driver_sql(sql)
            connection.execute(
                text("INSERT INTO app.schema_migration (filename) VALUES (:filename)"),
                {"filename": migration_path.name},
            )
