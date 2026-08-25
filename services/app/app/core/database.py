from functools import lru_cache

from sqlalchemy import Engine, create_engine, text

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    return create_engine(settings.database_url, pool_pre_ping=True, pool_size=5)


def check_database() -> bool:
    with get_engine().connect() as connection:
        return connection.execute(text("SELECT 1")).scalar_one() == 1


def read_project_stage() -> str:
    statement = text(
        "SELECT config_value #>> '{}' "
        "FROM app.app_config WHERE config_key = 'project_stage'"
    )
    with get_engine().connect() as connection:
        return connection.execute(statement).scalar_one_or_none() or "unknown"

