"""DCN — graph view over concerns and their relations.

This is a thin convenience layer on top of :class:`DCNStore`. The store is
the source of truth; this class is a domain-flavored facade for the rest
of the runtime.
"""

from __future__ import annotations

from opencoat_runtime_protocol import Concern, ConcernRelationType

from ..ports import DCNStore
from ..types import ConcernId


class DCNetwork:
    def __init__(self, *, store: DCNStore) -> None:
        self._store = store

    def upsert(self, concern: Concern) -> None:
        raise NotImplementedError

    def link(
        self,
        src: ConcernId,
        dst: ConcernId,
        relation: ConcernRelationType,
        *,
        weight: float = 1.0,
    ) -> None:
        raise NotImplementedError

    def neighbors(
        self, concern_id: ConcernId, *, relation: ConcernRelationType | None = None
    ) -> list[ConcernId]:
        raise NotImplementedError
