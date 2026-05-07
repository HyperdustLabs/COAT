"""Event Loop — non-turn-critical signals (v0.1 §22.2)."""

from __future__ import annotations


class EventLoop:
    def dispatch(self, event: dict) -> None:
        raise NotImplementedError
