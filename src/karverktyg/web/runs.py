"""
Background run management for write operations (CLAUDE.md §8).

Execute / resume / undo run in a background daemon thread so progress is
server-side state (the journal in Postgres) that the frontend polls; closing the
tab does not affect a run. At most one run is active at a time (§8, hard rule 5).
Dry-run is synchronous and does not go through here.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from sqlalchemy import select

from karverktyg.db import WriteRun, get_session


class RunBusy(RuntimeError):
    """A write run is already in progress — no concurrent writes (§8)."""


class RunManager:
    """Serialises write runs onto a single background thread."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    def launch(self, fn: Callable[[], None]) -> None:
        """
        Run ``fn`` in a background daemon thread. Raises ``RunBusy`` if a run is
        already in flight, so a second run can never overlap the first.
        """
        if not self._lock.acquire(blocking=False):
            raise RunBusy("a write run is already in progress")

        def _wrapped() -> None:
            try:
                fn()
            finally:
                self._lock.release()

        self._thread = threading.Thread(target=_wrapped, name="write-run", daemon=True)
        self._thread.start()

    def busy(self) -> bool:
        """Whether a run is active in this worker."""
        return self._lock.locked()

    def wait(self, timeout: float | None = None) -> None:
        """Join the background thread (tests, graceful shutdown)."""
        thread = self._thread
        if thread is not None:
            thread.join(timeout)


def run_active_in_db(sessionmaker: object) -> bool:
    """
    Whether any run is ``running`` per the database — the cross-worker guard.
    Under multiple gunicorn workers the in-memory lock only guards its own
    worker, so the endpoint also checks this before launching.
    """
    with get_session(sessionmaker) as s:
        return s.execute(select(WriteRun).where(WriteRun.state == "running")).first() is not None
