"""Concern Builder — v0.1 §20.3.

Normalizes candidate Concerns into proper :class:`Concern` instances and
upserts them through the configured :class:`ConcernStore`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from COAT_runtime_protocol import Concern

from ..ports import ConcernStore


class ConcernBuilder:
    def __init__(self, *, store: ConcernStore) -> None:
        self._store = store

    @staticmethod
    def new_id() -> str:
        return f"c-{uuid4().hex[:12]}"

    @staticmethod
    def now() -> datetime:
        return datetime.now(UTC)

    def build_or_update(self, candidate: Concern) -> Concern:
        """Normalize a candidate Concern and upsert it into the store."""
        raise NotImplementedError

    def build_many(self, candidates: list[Concern]) -> list[Concern]:
        raise NotImplementedError
