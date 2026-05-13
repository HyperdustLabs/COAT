"""Lifecycle / signal handling for the daemon (SIGTERM → drain → exit)."""

from __future__ import annotations


class Service:
    def install_signal_handlers(self) -> None:
        raise NotImplementedError

    def drain(self) -> None:
        raise NotImplementedError
