"""Concern Separator — v0.1 §20.2.

Handles Concern granularity: split too-large concerns, merge duplicates,
rewrite ambiguous ones, distinguish long-term vs transient concerns.
"""

from __future__ import annotations

from COAT_runtime_protocol import Concern


class ConcernSeparator:
    """Granularity manager for the candidate-concern stream."""

    def split(self, concern: Concern) -> list[Concern]:
        raise NotImplementedError

    def merge(self, a: Concern, b: Concern) -> Concern:
        raise NotImplementedError

    def rewrite(self, concern: Concern) -> Concern:
        raise NotImplementedError

    def classify_duration(self, concern: Concern) -> str:
        """Return one of ``transient`` / ``turn`` / ``session`` / ``long_term``."""
        raise NotImplementedError
