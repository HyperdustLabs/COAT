"""In-memory ConcernStore — skeleton.

M1 fills this in with a real dict-backed implementation that satisfies the
:class:`ConcernStore` protocol.
"""

from __future__ import annotations

from collections.abc import Iterable

from COAT_runtime_core.ports import ConcernStore
from COAT_runtime_protocol import Concern


class MemoryConcernStore(ConcernStore):
    def __init__(self) -> None:
        self._concerns: dict[str, Concern] = {}

    def upsert(self, concern: Concern) -> Concern:
        raise NotImplementedError

    def get(self, concern_id: str) -> Concern | None:
        raise NotImplementedError

    def delete(self, concern_id: str) -> None:
        raise NotImplementedError

    def list(
        self,
        *,
        kind: str | None = None,
        tag: str | None = None,
        lifecycle_state: str | None = None,
        limit: int | None = None,
    ) -> list[Concern]:
        raise NotImplementedError

    def search(self, query: str, *, limit: int = 20) -> list[Concern]:
        raise NotImplementedError

    def iter_all(self) -> Iterable[Concern]:
        raise NotImplementedError
