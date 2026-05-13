"""Persistence port for the Deep Concern Network (DCN)."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Protocol, runtime_checkable

from opencoat_runtime_protocol import Concern, ConcernRelationType

from ..types import ConcernId


@runtime_checkable
class DCNStore(Protocol):
    """Graph-shaped store for concerns + 13 relation types + activation history."""

    # nodes ------------------------------------------------------------------
    def add_node(self, concern: Concern) -> None: ...
    def remove_node(self, concern_id: ConcernId) -> None: ...

    # edges ------------------------------------------------------------------
    def add_edge(
        self,
        src: ConcernId,
        dst: ConcernId,
        relation_type: ConcernRelationType,
        *,
        weight: float = 1.0,
    ) -> None: ...
    def remove_edge(
        self, src: ConcernId, dst: ConcernId, relation_type: ConcernRelationType
    ) -> None: ...
    def neighbors(
        self,
        concern_id: ConcernId,
        *,
        relation_type: ConcernRelationType | None = None,
    ) -> list[ConcernId]: ...

    # history ----------------------------------------------------------------
    def log_activation(
        self,
        concern_id: ConcernId,
        joinpoint_id: str,
        score: float,
        ts: datetime,
    ) -> None: ...
    def activation_log(
        self,
        concern_id: ConcernId | None = None,
        *,
        limit: int | None = None,
    ) -> Iterable[dict]: ...

    # housekeeping -----------------------------------------------------------
    def merge(self, src: ConcernId, dst: ConcernId) -> None: ...
    def archive(self, concern_id: ConcernId) -> None: ...
