"""Top-K activation selection.

The selector is the **last gate** before the vector builder: it is given an
already-ranked list and returns at most ``k`` entries. Ranking is
preserved; if two scores tie the input order wins (and the ranker upstream
guarantees a deterministic tiebreaker, so this is stable end-to-end).
"""

from __future__ import annotations

from opencoat_runtime_protocol import Concern


class TopKSelector:
    """Trim a ranked list to its top-``k`` entries."""

    def select(
        self,
        scored: list[tuple[Concern, float]],
        k: int,
    ) -> list[tuple[Concern, float]]:
        if k <= 0:
            return []
        if k >= len(scored):
            return list(scored)
        return list(scored[:k])


__all__ = ["TopKSelector"]
