from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar


Result = TypeVar("Result")


def run_with_retry(
    operation: Callable[[], Result],
    *,
    attempts: int,
    delay_seconds: float,
    retryable_errors: tuple[type[BaseException], ...],
    on_retry: Callable[[BaseException, int, int], None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> Result:
    """Run a startup operation with a bounded, constant-delay retry policy."""
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    if delay_seconds < 0:
        raise ValueError("delay_seconds cannot be negative")

    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except retryable_errors as exc:
            if attempt == attempts:
                raise
            if on_retry is not None:
                on_retry(exc, attempt, attempts)
            sleep(delay_seconds)

    raise RuntimeError("unreachable")
