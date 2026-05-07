"""Heartbeat + periodic worker scheduler."""

from __future__ import annotations


class Scheduler:
    def __init__(self, *, heartbeat_interval_seconds: float = 30.0) -> None:
        self._interval = heartbeat_interval_seconds

    def start(self) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError
