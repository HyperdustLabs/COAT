"""Concern Resolver — v0.1 §20.8."""

from __future__ import annotations

from COAT_runtime_protocol import Concern

from .conflict import ConflictResolver
from .dedupe import Dedupe
from .escalation import EscalationManager


class ConcernResolver:
    def __init__(
        self,
        *,
        conflict: ConflictResolver | None = None,
        dedupe: Dedupe | None = None,
        escalation: EscalationManager | None = None,
    ) -> None:
        self._conflict = conflict or ConflictResolver()
        self._dedupe = dedupe or Dedupe()
        self._escalation = escalation or EscalationManager()

    def resolve(self, ranked: list[tuple[Concern, float]]) -> list[tuple[Concern, float]]:
        raise NotImplementedError
