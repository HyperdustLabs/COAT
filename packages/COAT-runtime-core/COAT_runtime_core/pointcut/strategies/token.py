"""Exact token / sub-token match strategy."""

from __future__ import annotations

from ._base import JSON, JoinpointEvent, MatchResult


def apply(jp: JoinpointEvent, tokens: list[str], context: JSON | None = None) -> MatchResult:
    """Match when *any* token in ``tokens`` appears in the joinpoint payload."""
    raise NotImplementedError
