from __future__ import annotations

import logging

from sqlalchemy.exc import OperationalError

from app.catalog.service import refresh_catalog
from app.core.config import get_settings
from app.core.database import get_engine
from app.core.migrations import run_migrations
from app.core.retry import run_with_retry
from app.rag.indexer import ensure_index


logger = logging.getLogger(__name__)


def initialize_application() -> None:
    """Apply migrations and prepare catalog/RAG data before serving traffic."""
    run_migrations()
    refresh_catalog()
    ensure_index()


def initialize_application_with_retry() -> None:
    """Tolerate PostgreSQL's short first-boot window without a fixed sleep."""
    settings = get_settings()

    def on_retry(exc: BaseException, attempt: int, attempts: int) -> None:
        get_engine().dispose()
        logger.warning(
            "Database startup is not ready; retrying application bootstrap (%s/%s): %s",
            attempt,
            attempts,
            type(exc).__name__,
        )

    run_with_retry(
        initialize_application,
        attempts=settings.startup_max_attempts,
        delay_seconds=settings.startup_retry_delay_seconds,
        retryable_errors=(OperationalError,),
        on_retry=on_retry,
    )
