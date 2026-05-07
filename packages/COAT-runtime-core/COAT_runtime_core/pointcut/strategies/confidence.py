"""Confidence-score comparison strategy."""

from __future__ import annotations

from ._base import JSON, JoinpointEvent, MatchResult


def apply(
    jp: JoinpointEvent,
    *,
    op: str,
    threshold: float,
    context: JSON | None = None,
) -> MatchResult:
    """Compare ``context['confidence']`` (or joinpoint payload confidence)
    against ``threshold`` using ``op`` (``< / <= / > / >=``)."""
    raise NotImplementedError
