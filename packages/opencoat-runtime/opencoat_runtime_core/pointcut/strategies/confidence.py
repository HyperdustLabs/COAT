"""Confidence-score comparison strategy."""

from __future__ import annotations

from .._context import MISSING_VALUE, context_lookup
from .._text import MISSING, payload_field
from ._base import JSON, NO_MATCH, JoinpointEvent, MatchResult, make_match

_OPERATORS = {"<", "<=", ">", ">="}


def apply(
    jp: JoinpointEvent,
    *,
    op: str,
    threshold: float,
    context: JSON | None = None,
) -> MatchResult:
    """Compare confidence against ``threshold`` using ``op``.

    The confidence value is read from ``context['confidence']`` first, then
    falls back to ``payload.confidence``. Missing values produce no match.
    """
    if op not in _OPERATORS:
        raise ValueError(f"unsupported confidence operator: {op!r}")

    value: object | float = context_lookup(context, "confidence")
    if value is MISSING_VALUE:
        looked_up = payload_field(jp.payload, "confidence")
        if looked_up is MISSING:
            return NO_MATCH
        value = looked_up

    try:
        score = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return NO_MATCH

    matches = (
        score < threshold
        if op == "<"
        else score <= threshold
        if op == "<="
        else score > threshold
        if op == ">"
        else score >= threshold
    )
    if not matches:
        return NO_MATCH
    return make_match(1.0, f"confidence:{score} {op} {threshold}")
