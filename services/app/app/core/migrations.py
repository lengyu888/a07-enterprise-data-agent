from pathlib import Path

from sqlalchemy import text

from app.core.database import get_engine


MIGRATIONS_DIR = Path("/workspace/migrations")


def run_migrations() -> None:
    if not MIGRATIONS_DIR.is_dir():
        return

    engine = get_engine()
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE IF NOT EXISTS app.schema_migration ("
                "filename TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW())"
            )
        )

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
