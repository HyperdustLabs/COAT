"""Concern conflict resolver — uses the ``conflicts_with`` and ``suppresses`` relations."""

from __future__ import annotations

from COAT_runtime_protocol import Concern


class ConflictResolver:
    def detect(self, concerns: list[Concern]) -> list[tuple[Concern, Concern]]:
        raise NotImplementedError

    def resolve(self, ranked: list[tuple[Concern, float]]) -> list[tuple[Concern, float]]:
        raise NotImplementedError
