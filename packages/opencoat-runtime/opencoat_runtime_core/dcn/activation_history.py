"""Per-concern activation history."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from ..ports import DCNStore
from ..types import ConcernId


class ActivationHistory:
    def __init__(self, *, store: DCNStore) -> None:
        self._store = store

    def log(self, concern_id: ConcernId, joinpoint_id: str, score: float, ts: datetime) -> None:
        raise NotImplementedError

    def query(
        self,
        concern_id: ConcernId | None = None,
        *,
        limit: int | None = None,
    ) -> Iterable[dict]:
        raise NotImplementedError
