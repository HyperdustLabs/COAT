"""In-memory :class:`ConcernStore` implementation.

This is the M1 default backend. It satisfies
:class:`opencoat_runtime_core.ports.ConcernStore` with simple dict-backed storage.

The store performs *defensive copies* of every Concern that crosses its
boundary so that callers can mutate returned objects without corrupting
in-store state, and vice-versa. This makes the contract testable and
matches the semantics that real persistence backends (sqlite, postgres)
will provide naturally.

Search is intentionally minimal at M1: case-insensitive substring matching
over ``name`` and ``description``. Embedding-based semantic search is the
remit of ``opencoat_runtime_storage.vector`` and arrives in M2+.
"""

from __future__ import annotations

import threading
from collections.abc import Iterable

from opencoat_runtime_core.ports import ConcernStore
from opencoat_runtime_protocol import Concern

from ..query import Filter, apply_filter, substring_match


class MemoryConcernStore(ConcernStore):
    """Dict-backed Concern store, ordered by insertion."""

    def __init__(self) -> None:
        self._concerns: dict[str, Concern] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def upsert(self, concern: Concern) -> Concern:
        if not concern.id:
            raise ValueError("Concern.id must be a non-empty string")
        snapshot = concern.model_copy(deep=True)
        with self._lock:
            self._concerns[concern.id] = snapshot
        return snapshot.model_copy(deep=True)

    def get(self, concern_id: str) -> Concern | None:
        with self._lock:
            stored = self._concerns.get(concern_id)
        return stored.model_copy(deep=True) if stored is not None else None

    def delete(self, concern_id: str) -> None:
        with self._lock:
            self._concerns.pop(concern_id, None)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def list(
        self,
        *,
        kind: str | None = None,
        tag: str | None = None,
        lifecycle_state: str | None = None,
        limit: int | None = None,
    ) -> list[Concern]:
        flt: Filter = {
            "kind": kind,
            "tag": tag,
            "lifecycle_state": lifecycle_state,
        }
        with self._lock:
            results = [
                c.model_copy(deep=True) for c in self._concerns.values() if apply_filter(c, flt)
            ]
        if limit is not None:
            results = results[: max(0, limit)]
        return results

    def search(self, query: str, *, limit: int = 20) -> list[Concern]:
        needle = query.strip().lower()
        if not needle:
            return []
        with self._lock:
            hits = [
                c.model_copy(deep=True)
                for c in self._concerns.values()
                if substring_match(c, needle)
            ]
        return hits[: max(0, limit)]

    def iter_all(self) -> Iterable[Concern]:
        with self._lock:
            snapshot = list(self._concerns.values())
        for concern in snapshot:
            yield concern.model_copy(deep=True)

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        with self._lock:
            return len(self._concerns)

    def __contains__(self, concern_id: object) -> bool:
        if not isinstance(concern_id, str):
            return False
        with self._lock:
            return concern_id in self._concerns

    def clear(self) -> None:
        """Drop every stored concern. Test/debug helper."""
        with self._lock:
            self._concerns.clear()


__all__ = ["MemoryConcernStore"]
