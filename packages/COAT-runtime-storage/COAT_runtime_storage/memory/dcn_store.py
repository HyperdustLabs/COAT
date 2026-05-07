"""In-memory :class:`DCNStore` implementation.

Adjacency-list style graph backed by plain dicts. Suitable for unit tests,
single-process daemons, and the M1 in-proc happy path.

Design notes
------------
* Nodes are stored as deep copies of the input :class:`Concern` so callers
  cannot mutate in-store state by retaining a reference.
* Edges are keyed by ``(src, dst, relation_type)`` so multiple distinct
  relations between the same two concerns coexist (e.g. ``activates`` and
  ``constrains``).
* :meth:`add_edge` and :meth:`log_activation` reject references to
  unknown nodes — this catches DCN-construction bugs early instead of
  letting them surface as silent dangling pointers.
* :meth:`merge` rewires every edge and activation record pointing at
  ``src`` so they reference ``dst`` instead, then removes ``src``.
* All operations take a re-entrant lock so the store can be shared
  across worker threads in the daemon.
"""

from __future__ import annotations

import threading
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from COAT_runtime_core.ports import DCNStore
from COAT_runtime_protocol import Concern, ConcernRelationType, LifecycleState

EdgeKey = tuple[str, str, str]  # (src, dst, relation_type-as-str)


def _rel_key(rel: ConcernRelationType | str) -> str:
    """Normalise a relation_type to its string form (matches use_enum_values)."""
    return rel.value if isinstance(rel, ConcernRelationType) else rel


class MemoryDCNStore(DCNStore):
    """Dict-backed graph store for the Deep Concern Network."""

    def __init__(self) -> None:
        self._nodes: dict[str, Concern] = {}
        self._edges: dict[EdgeKey, float] = {}
        self._activations: list[dict[str, Any]] = []
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Nodes
    # ------------------------------------------------------------------

    def add_node(self, concern: Concern) -> None:
        if not concern.id:
            raise ValueError("Concern.id must be a non-empty string")
        with self._lock:
            self._nodes[concern.id] = concern.model_copy(deep=True)

    def remove_node(self, concern_id: str) -> None:
        with self._lock:
            self._nodes.pop(concern_id, None)
            self._edges = {
                key: w
                for key, w in self._edges.items()
                if key[0] != concern_id and key[1] != concern_id
            }
            self._activations = [
                rec for rec in self._activations if rec["concern_id"] != concern_id
            ]

    def get_node(self, concern_id: str) -> Concern | None:
        """Convenience accessor — not part of the port, useful for tests."""
        with self._lock:
            stored = self._nodes.get(concern_id)
        return stored.model_copy(deep=True) if stored is not None else None

    # ------------------------------------------------------------------
    # Edges
    # ------------------------------------------------------------------

    def add_edge(
        self,
        src: str,
        dst: str,
        relation_type: ConcernRelationType,
        *,
        weight: float = 1.0,
    ) -> None:
        if not 0.0 <= weight <= 1.0:
            raise ValueError(f"weight must be in [0.0, 1.0], got {weight}")
        with self._lock:
            if src not in self._nodes:
                raise KeyError(f"unknown src concern: {src!r}")
            if dst not in self._nodes:
                raise KeyError(f"unknown dst concern: {dst!r}")
            self._edges[(src, dst, _rel_key(relation_type))] = weight

    def remove_edge(self, src: str, dst: str, relation_type: ConcernRelationType) -> None:
        with self._lock:
            self._edges.pop((src, dst, _rel_key(relation_type)), None)

    def neighbors(
        self,
        concern_id: str,
        *,
        relation_type: ConcernRelationType | None = None,
    ) -> list[str]:
        wanted = _rel_key(relation_type) if relation_type is not None else None
        with self._lock:
            seen: list[str] = []
            seen_set: set[str] = set()
            for src, dst, rel in self._edges:
                if src != concern_id:
                    continue
                if wanted is not None and rel != wanted:
                    continue
                if dst not in seen_set:
                    seen.append(dst)
                    seen_set.add(dst)
            return seen

    def edge_weight(self, src: str, dst: str, relation_type: ConcernRelationType) -> float | None:
        """Convenience accessor — not part of the port, useful for tests."""
        with self._lock:
            return self._edges.get((src, dst, _rel_key(relation_type)))

    # ------------------------------------------------------------------
    # Activation history
    # ------------------------------------------------------------------

    def log_activation(
        self,
        concern_id: str,
        joinpoint_id: str,
        score: float,
        ts: datetime,
    ) -> None:
        if not 0.0 <= score <= 1.0:
            raise ValueError(f"score must be in [0.0, 1.0], got {score}")
        with self._lock:
            if concern_id not in self._nodes:
                raise KeyError(f"unknown concern: {concern_id!r}")
            self._activations.append(
                {
                    "concern_id": concern_id,
                    "joinpoint_id": joinpoint_id,
                    "score": score,
                    "ts": ts,
                }
            )

    def activation_log(
        self,
        concern_id: str | None = None,
        *,
        limit: int | None = None,
    ) -> Iterable[dict]:
        with self._lock:
            records = (
                self._activations
                if concern_id is None
                else [r for r in self._activations if r["concern_id"] == concern_id]
            )
            snapshot = [dict(r) for r in records]
        if limit is not None:
            if limit <= 0:
                return []
            snapshot = snapshot[-limit:]
        return snapshot

    # ------------------------------------------------------------------
    # Housekeeping
    # ------------------------------------------------------------------

    def merge(self, src: str, dst: str) -> None:
        if src == dst:
            return
        with self._lock:
            if src not in self._nodes:
                raise KeyError(f"unknown src concern: {src!r}")
            if dst not in self._nodes:
                raise KeyError(f"unknown dst concern: {dst!r}")

            rewired: dict[EdgeKey, float] = {}
            for (s, d, rel), weight in self._edges.items():
                ns = dst if s == src else s
                nd = dst if d == src else d
                if ns == nd:
                    continue
                key = (ns, nd, rel)
                rewired[key] = max(rewired.get(key, 0.0), weight)
            self._edges = rewired

            for rec in self._activations:
                if rec["concern_id"] == src:
                    rec["concern_id"] = dst

            self._nodes.pop(src, None)

    def archive(self, concern_id: str) -> None:
        with self._lock:
            stored = self._nodes.get(concern_id)
            if stored is None:
                return
            stored.lifecycle_state = LifecycleState.ARCHIVED.value

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        with self._lock:
            return len(self._nodes)

    def __contains__(self, concern_id: object) -> bool:
        if not isinstance(concern_id, str):
            return False
        with self._lock:
            return concern_id in self._nodes

    def edge_count(self) -> int:
        with self._lock:
            return len(self._edges)


__all__ = ["MemoryDCNStore"]
