"""Top-K activation selection."""

from __future__ import annotations

from COAT_runtime_protocol import Concern


class TopKSelector:
    def select(self, scored: list[tuple[Concern, float]], k: int) -> list[tuple[Concern, float]]:
        raise NotImplementedError
