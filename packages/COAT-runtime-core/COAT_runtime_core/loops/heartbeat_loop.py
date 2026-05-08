"""Heartbeat Loop — long-term DCN maintenance (v0.1 §22.3).

The heartbeat is the runtime's slow drumbeat: it scans the DCN for
decay, conflicts, merge candidates, and meta-review opportunities. In
M1 the implementation is deliberately *no-op* — the loop walks the
stores, counts work-items, and emits observer metrics, but it does not
mutate concerns yet. The real decay / merge / archive logic lands in
M2 when the lifecycle manager and DCN evolution module are wired up.

Returning a populated ``HeartbeatReport`` even in the no-op M1 case
gives hosts a stable observability surface today, so M2 can swap in
real maintenance without breaking the report shape.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from ..ports import ConcernStore, DCNStore, Observer
from ..ports.observer import NullObserver


@dataclass(frozen=True)
class HeartbeatReport:
    """Outcome of one heartbeat tick."""

    ts: datetime
    decay_count: int = 0
    merge_count: int = 0
    archive_count: int = 0
    conflict_count: int = 0
    candidate_count: int = 0


class HeartbeatLoop:
    """Walk the stores; emit observability; mutate nothing (M1)."""

    def __init__(
        self,
        *,
        concern_store: ConcernStore,
        dcn_store: DCNStore,
        observer: Observer | None = None,
    ) -> None:
        self._concern_store = concern_store
        self._dcn_store = dcn_store
        self._observer = observer or NullObserver()

    def tick(self, now: datetime | None = None) -> HeartbeatReport:
        ts = now or datetime.now(UTC)
        with self._observer.on_span("COAT.heartbeat", ts=ts.isoformat()):
            # Cheap inventory sweep — the M2 implementation will replace
            # this with the decay / conflict / merge / archive walkers.
            candidates = sum(1 for _ in self._concern_store.iter_all())
            self._observer.on_metric("COAT.heartbeat.concern_count", float(candidates))
            return HeartbeatReport(ts=ts, candidate_count=candidates)


__all__ = ["HeartbeatLoop", "HeartbeatReport"]
