"""Lifecycle-stage pointcut strategy."""

from __future__ import annotations

from ._base import JSON, JoinpointEvent, MatchResult


def apply(
    jp: JoinpointEvent, expected_stages: list[str], context: JSON | None = None
) -> MatchResult:
    """Match if the joinpoint's lifecycle stage is in ``expected_stages``."""
    raise NotImplementedError
