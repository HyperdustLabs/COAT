"""Regex pointcut strategy."""

from __future__ import annotations

from ._base import JSON, JoinpointEvent, MatchResult


def apply(jp: JoinpointEvent, pattern: str, context: JSON | None = None) -> MatchResult:
    """Match if ``pattern`` matches the joinpoint's textual payload."""
    raise NotImplementedError
