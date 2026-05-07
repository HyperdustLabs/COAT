"""Structured-field comparison strategy.

Looks up ``field`` in the joinpoint payload (dotted path), then applies one
of the operators allowed by the schema. ``value_ref`` resolves the
comparison value through the runtime context instead of being literal.
"""

from __future__ import annotations

from typing import Any

from .._context import (
    MISSING_VALUE,
    STRUCTURE_OPERATORS,
    apply_operator,
    resolve_value,
)
from .._text import MISSING, payload_field
from ._base import JSON, NO_MATCH, JoinpointEvent, MatchResult, make_match


def apply(
    jp: JoinpointEvent,
    *,
    field: str,
    operator: str,
    value: Any | None = None,
    value_ref: str | None = None,
    context: JSON | None = None,
) -> MatchResult:
    if operator not in STRUCTURE_OPERATORS:
        raise ValueError(f"unsupported structure operator: {operator!r}")

    target = payload_field(jp.payload, field)
    if target is MISSING:
        return NO_MATCH

    compare = resolve_value(value=value, value_ref=value_ref, context=context)
    if compare is MISSING_VALUE:
        return NO_MATCH

    if apply_operator(operator, target, compare):
        return make_match(1.0, f"structure:{field} {operator} {compare!r}")
    return NO_MATCH
