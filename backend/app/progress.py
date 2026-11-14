"""Which step each person's brief is on, so the ask page can show real progress while it waits.

A brief takes 10-75 s with a hosted model, most of it in the writer and, when the checks send a draft
back, a second writing pass. The brief request runs in the server's thread pool; the page polls
GET /api/briefs/progress meanwhile. Kept in memory per user: it is a display aid, lost on restart
and never audited. One brief at a time per person; a second request simply overwrites the first.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

# Indexes match the step list on the ask page (frontend/app/page.tsx, STEPS).
SEARCH, COMPARE, WRITE, CHECK = range(4)

_lock = threading.Lock()
_state: dict[str, dict] = {}
_STALE_SECONDS = 600


def reporter(user_id: str) -> Callable[[int, str | None], None]:
    def report(step: int, detail: str | None = None) -> None:
        with _lock:
            _state[user_id] = {"step": step, "detail": detail, "at": time.time()}
    return report


def current(user_id: str) -> dict | None:
    with _lock:
        state = _state.get(user_id)
        if state and time.time() - state["at"] > _STALE_SECONDS:
            _state.pop(user_id, None)
            return None
        return {"step": state["step"], "detail": state["detail"]} if state else None


def clear(user_id: str) -> None:
    with _lock:
        _state.pop(user_id, None)


def ignore(step: int, detail: str | None = None) -> None:
    """The default reporter: briefs made outside a web request (evals, tests) report nowhere."""
