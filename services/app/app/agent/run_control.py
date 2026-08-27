from __future__ import annotations

from threading import Lock
from time import monotonic


class RunCancelledError(RuntimeError):
    pass


_cancelled: dict[str, float] = {}
_lock = Lock()
_RETENTION_SECONDS = 600.0


def _prune(now: float) -> None:
    expired = [run_id for run_id, requested_at in _cancelled.items() if now - requested_at > _RETENTION_SECONDS]
    for run_id in expired:
        _cancelled.pop(run_id, None)


def request_cancellation(run_id: str) -> None:
    now = monotonic()
    with _lock:
        _prune(now)
        _cancelled[run_id] = now


def clear_cancellation(run_id: str) -> None:
    with _lock:
        _cancelled.pop(run_id, None)


def is_cancellation_requested(run_id: str) -> bool:
    now = monotonic()
    with _lock:
        _prune(now)
        return run_id in _cancelled


def ensure_not_cancelled(run_id: str) -> None:
    if is_cancellation_requested(run_id):
        raise RunCancelledError("本次 Agent 运行已由用户取消")
