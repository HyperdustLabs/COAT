"""Priority ranker — combines relevance / priority / trust / recency / history.

Default formula (v0.1 §18):

    activation = relevance + priority + trust + recency + history_effectiveness
                 - conflict_penalty - budget_penalty
"""

from __future__ import annotations

from COAT_runtime_protocol import Concern


class PriorityRanker:
    def rank(
        self,
        scored: list[tuple[Concern, float]],
        *,
        context: dict | None = None,
    ) -> list[tuple[Concern, float]]:
        raise NotImplementedError
