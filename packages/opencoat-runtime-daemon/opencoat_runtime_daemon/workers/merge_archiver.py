"""Periodic merge / archive worker."""

from __future__ import annotations

from datetime import datetime

from ._base import Worker


class MergeArchiverWorker(Worker):
    def run(self, now: datetime) -> dict:
        raise NotImplementedError
