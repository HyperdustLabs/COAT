"""Queue-driven batch extraction worker."""

from __future__ import annotations

from datetime import datetime

from ._base import Worker


class ExtractionWorker(Worker):
    def run(self, now: datetime) -> dict:
        raise NotImplementedError
