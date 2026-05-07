"""Keyword (any/all) match strategy."""

from __future__ import annotations

from ._base import JSON, JoinpointEvent, MatchResult


def apply(
    jp: JoinpointEvent,
    *,
    any_keywords: list[str] | None = None,
    all_keywords: list[str] | None = None,
    case_sensitive: bool = False,
    context: JSON | None = None,
) -> MatchResult:
    """OR over ``any_keywords``, AND over ``all_keywords``."""
    raise NotImplementedError
