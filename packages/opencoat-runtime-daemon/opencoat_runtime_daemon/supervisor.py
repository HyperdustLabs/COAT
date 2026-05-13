"""Worker supervisor — restart workers that crash."""

from __future__ import annotations


class Supervisor:
    def supervise(self) -> None:
        raise NotImplementedError
