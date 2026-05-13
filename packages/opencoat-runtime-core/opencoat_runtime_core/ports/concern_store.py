"""Persistence port for Concerns."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from opencoat_runtime_protocol import Concern

from ..types import ConcernId


@runtime_checkable
class ConcernStore(Protocol):
    """CRUD + simple search over concerns.

    Implementations live in ``opencoat-runtime-storage``; the core's only
    requirement is that they obey this protocol.
    """

    def upsert(self, concern: Concern) -> Concern: ...
    def get(self, concern_id: ConcernId) -> Concern | None: ...
    def delete(self, concern_id: ConcernId) -> None: ...
    def list(
        self,
        *,
        kind: str | None = None,
        tag: str | None = None,
        lifecycle_state: str | None = None,
        limit: int | None = None,
    ) -> list[Concern]: ...
    def search(self, query: str, *, limit: int = 20) -> list[Concern]: ...
    def iter_all(self) -> Iterable[Concern]: ...
