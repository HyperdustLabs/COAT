"""Message-role pointcut strategy."""

from __future__ import annotations

from ._base import JSON, JoinpointEvent, MatchResult


def apply(
    jp: JoinpointEvent, expected_roles: list[str], context: JSON | None = None
) -> MatchResult:
    """Match if the joinpoint's message role is in ``expected_roles``."""
    raise NotImplementedError
