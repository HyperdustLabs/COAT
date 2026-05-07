"""Top-level :class:`Daemon` class — composes Runtime + IPC + Scheduler."""

from __future__ import annotations

from .config.loader import DaemonConfig


class Daemon:
    def __init__(self, config: DaemonConfig) -> None:
        self._config = config

    def start(self) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError

    def reload(self) -> None:
        raise NotImplementedError
