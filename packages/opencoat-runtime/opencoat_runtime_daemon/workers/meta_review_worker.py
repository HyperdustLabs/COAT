"""Meta-concern review worker (runs the 8 governance capabilities)."""

from __future__ import annotations

from datetime import datetime

from ._base import Worker


class MetaReviewWorker(Worker):
    def run(self, now: datetime) -> dict:
        raise NotImplementedError
