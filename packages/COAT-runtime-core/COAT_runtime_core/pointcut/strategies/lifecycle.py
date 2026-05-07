"""Lifecycle-stage pointcut strategy."""

from __future__ import annotations

from ._base import JSON, NO_MATCH, JoinpointEvent, MatchResult, make_match


def apply(
    jp: JoinpointEvent, expected_stages: list[str], context: JSON | None = None
) -> MatchResult:
    """Match if the joinpoint's lifecycle stage is in ``expected_stages``.

    The stage is read from ``payload.stage`` (lifecycle payload kind) and
    falls back to ``jp.name`` so the strategy works for joinpoints emitted
    with only a catalog name.
    """
    if not expected_stages:
        return NO_MATCH
    payload = jp.payload or {}
    stage = payload.get("stage") if isinstance(payload.get("stage"), str) else jp.name
    if not stage:
        return NO_MATCH
    if stage in expected_stages:
        return make_match(1.0, f"lifecycle:{stage}")
    return NO_MATCH
