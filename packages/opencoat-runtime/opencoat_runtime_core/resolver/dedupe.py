"""Concern deduplication — collapses ``duplicates`` style relations.

Two concerns are considered duplicates if either side carries a
``generalizes`` / ``specializes`` relation pointing at the other and the
relation weight is ``>= 0.5``. The narrower (``specializes``) variant is
preferred when both are activated; otherwise the first occurrence wins so
ranking is preserved.

The official taxonomy does not yet include a dedicated ``duplicates``
relation type; we keep the pluggable seam (configurable predicate) so
M2 / DCN promotion can introduce one without touching call-sites.
"""

from __future__ import annotations

from opencoat_runtime_protocol import Concern, ConcernRelationType


class Dedupe:
    """Collapse duplicate concerns based on DCN relations."""

    _DUPLICATE_RELATIONS = frozenset(
        {
            ConcernRelationType.GENERALIZES,
            ConcernRelationType.SPECIALIZES,
        }
    )
    _MIN_WEIGHT = 0.5

    def collapse(self, concerns: list[Concern]) -> list[Concern]:
        if not concerns:
            return []

        index = {c.id: c for c in concerns}
        dropped: set[str] = set()

        for concern in concerns:
            if concern.id in dropped:
                continue
            for rel in concern.relations:
                if rel.relation_type not in self._DUPLICATE_RELATIONS:
                    continue
                if rel.weight < self._MIN_WEIGHT:
                    continue
                target = index.get(rel.target_concern_id)
                if target is None or target.id in dropped:
                    continue
                loser = self._pick_loser(concern, target, rel.relation_type)
                dropped.add(loser)
                if loser == concern.id:
                    break  # this concern is gone; stop scanning its relations

        return [c for c in concerns if c.id not in dropped]

    @staticmethod
    def _pick_loser(
        concern: Concern,
        target: Concern,
        relation: ConcernRelationType,
    ) -> str:
        # Prefer the more specific concern: if A specializes B, drop B.
        if relation == ConcernRelationType.SPECIALIZES:
            return target.id
        if relation == ConcernRelationType.GENERALIZES:
            return concern.id
        return target.id  # defensive default


__all__ = ["Dedupe"]
