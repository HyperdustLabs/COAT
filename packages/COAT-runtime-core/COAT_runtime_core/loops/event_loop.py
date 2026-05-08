"""Event Loop — non-turn-critical signals (v0.1 §22.2).

The event loop owns *off-turn* signals: tool results, environment events,
async user feedback, etc. M1 keeps the implementation deliberately narrow:

* Events are appended to an in-memory queue (FIFO).
* :meth:`drain` returns and clears the queue so callers can process
  events at their own cadence (typically the heartbeat tick).
* Subscribers can register callbacks via :meth:`subscribe`; every
  :meth:`dispatch` call fans the event out to subscribers synchronously
  before returning. Callbacks that raise are isolated so one buggy
  subscriber cannot stall the loop.

The event loop is intentionally synchronous in M1; the real async
queue + worker pool ships in M2 once we have a host that needs it.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from ..ports import Observer
from ..ports.observer import NullObserver

EventCallback = Callable[[dict[str, Any]], None]


class EventLoop:
    """Thread-safe in-memory event queue + sync fan-out."""

    def __init__(self, *, observer: Observer | None = None) -> None:
        self._queue: list[dict[str, Any]] = []
        self._subscribers: list[EventCallback] = []
        self._observer = observer or NullObserver()
        self._lock = threading.Lock()

    def dispatch(self, event: dict[str, Any]) -> None:
        """Append the event to the queue and fan out to subscribers."""
        with self._lock:
            self._queue.append(dict(event))
            subs = list(self._subscribers)

        for cb in subs:
            try:
                cb(event)
            except Exception as exc:
                self._observer.on_log(
                    "error",
                    "event subscriber raised",
                    callback=getattr(cb, "__name__", repr(cb)),
                    error=repr(exc),
                )

    def subscribe(self, callback: EventCallback) -> None:
        with self._lock:
            self._subscribers.append(callback)

    def drain(self) -> list[dict[str, Any]]:
        """Return + clear the pending queue (FIFO)."""
        with self._lock:
            pending = self._queue
            self._queue = []
        return pending

    @property
    def pending_count(self) -> int:
        with self._lock:
            return len(self._queue)


__all__ = ["EventCallback", "EventLoop"]
