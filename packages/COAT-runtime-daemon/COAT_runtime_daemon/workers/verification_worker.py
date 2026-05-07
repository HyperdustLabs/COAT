"""Asynchronous verification worker."""

from __future__ import annotations

from datetime import datetime

from ._base import Worker


class VerificationWorker(Worker):
    def run(self, now: datetime) -> dict:
        raise NotImplementedError
