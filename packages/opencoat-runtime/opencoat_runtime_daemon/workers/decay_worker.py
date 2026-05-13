"""Concern-decay worker — runs on heartbeat."""

from __future__ import annotations

from datetime import datetime

from ._base import Worker


class DecayWorker(Worker):
    def run(self, now: datetime) -> dict:
        raise NotImplementedError
