"""In-memory DCNStore — skeleton.

M1 fills this in with adjacency-list dicts.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from COAT_runtime_core.ports import DCNStore
from COAT_runtime_protocol import Concern, ConcernRelationType


class MemoryDCNStore(DCNStore):
    def __init__(self) -> None:
        self._nodes: dict[str, Concern] = {}
        self._edges: dict[tuple[str, str, ConcernRelationType], float] = {}
        self._activations: list[dict] = []

    def add_node(self, concern: Concern) -> None:
        raise NotImplementedError

    def remove_node(self, concern_id: str) -> None:
        raise NotImplementedError

    def add_edge(
        self,
        src: str,
        dst: str,
        relation_type: ConcernRelationType,
        *,
        weight: float = 1.0,
    ) -> None:
        raise NotImplementedError

    def remove_edge(self, src: str, dst: str, relation_type: ConcernRelationType) -> None:
        raise NotImplementedError

    def neighbors(
        self,
        concern_id: str,
        *,
        relation_type: ConcernRelationType | None = None,
    ) -> list[str]:
        raise NotImplementedError

    def log_activation(
        self, concern_id: str, joinpoint_id: str, score: float, ts: datetime
    ) -> None:
        raise NotImplementedError

    def activation_log(
        self, concern_id: str | None = None, *, limit: int | None = None
    ) -> Iterable[dict]:
        raise NotImplementedError

    def merge(self, src: str, dst: str) -> None:
        raise NotImplementedError

    def archive(self, concern_id: str) -> None:
        raise NotImplementedError
