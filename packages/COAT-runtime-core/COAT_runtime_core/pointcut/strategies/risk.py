"""Risk-level comparison strategy."""

from __future__ import annotations

from ._base import JSON, JoinpointEvent, MatchResult

LEVELS = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def apply(jp: JoinpointEvent, *, op: str, level: str, context: JSON | None = None) -> MatchResult:
    """Compare ``context['risk_level']`` against ``level`` using ``op``."""
    raise NotImplementedError
