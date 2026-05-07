"""Periodic conflict scanner — populates ``conflicts_with`` edges."""

from __future__ import annotations

from datetime import datetime

from ._base import Worker


class ConflictScannerWorker(Worker):
    def run(self, now: datetime) -> dict:
        raise NotImplementedError
