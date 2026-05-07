"""Risk-level comparison strategy."""

from __future__ import annotations

from .._context import MISSING_VALUE, context_lookup
from .._text import MISSING, payload_field
from ._base import JSON, NO_MATCH, JoinpointEvent, MatchResult, make_match

LEVELS: dict[str, int] = {"low": 0, "medium": 1, "high": 2, "critical": 3}
_OPERATORS = {"==", ">=", "<="}


def apply(jp: JoinpointEvent, *, op: str, level: str, context: JSON | None = None) -> MatchResult:
    """Compare risk against ``level`` using ``op`` (``== / >= / <=``).

    Risk source: ``context['risk_level']`` first, then ``payload.risk_level``.
    Both target and threshold must resolve to one of
    ``low / medium / high / critical``; everything else is no match.
    """
    if op not in _OPERATORS:
        raise ValueError(f"unsupported risk operator: {op!r}")
    if level not in LEVELS:
        raise ValueError(f"unknown risk level: {level!r}")

    value: object | str = context_lookup(context, "risk_level")
    if value is MISSING_VALUE:
        looked_up = payload_field(jp.payload, "risk_level")
        if looked_up is MISSING:
            return NO_MATCH
        value = looked_up

    if not isinstance(value, str) or value not in LEVELS:
        return NO_MATCH

    target = LEVELS[value]
    threshold = LEVELS[level]
    matches = (
        target == threshold
        if op == "=="
        else target >= threshold
        if op == ">="
        else target <= threshold
    )
    if not matches:
        return NO_MATCH
    return make_match(1.0, f"risk:{value} {op} {level}")
