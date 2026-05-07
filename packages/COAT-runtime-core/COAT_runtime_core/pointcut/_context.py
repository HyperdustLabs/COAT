"""Context-side helpers — value resolution and operator dispatch.

The pointcut schema lets several strategies reference values either
*literally* (``value: 1000``) or *by reference* into the runtime context
(``value_ref: "risk_budget.max_amount"``). Both ``structure`` and the
top-level ``context_predicates`` use the same machinery; we centralise it
here so the semantics stay consistent.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..types import JSON
from ._text import MISSING, payload_field


def resolve_value(
    *,
    value: Any | None,
    value_ref: str | None,
    context: JSON | None,
) -> object | _MissingMarker:
    """Resolve the comparison value used by a structure/context predicate.

    ``value_ref`` wins when given. A missing context lookup yields
    :data:`MISSING_VALUE` so callers can distinguish "found None" from
    "not in context".
    """
    if value_ref is not None:
        if context is None:
            return MISSING_VALUE
        looked_up = payload_field(context, value_ref)
        if looked_up is MISSING:
            return MISSING_VALUE
        return looked_up
    return value


def context_lookup(context: JSON | None, dotted: str) -> object | _MissingMarker:
    """Public wrapper around :func:`payload_field` for the context map."""
    if context is None:
        return MISSING_VALUE
    looked_up = payload_field(context, dotted)
    return MISSING_VALUE if looked_up is MISSING else looked_up


# ---------------------------------------------------------------------------
# Operator dispatch
# ---------------------------------------------------------------------------

#: Operators legal in the JSON Schema for ``structure`` matchers.
STRUCTURE_OPERATORS = frozenset({"==", "!=", ">", ">=", "<", "<=", "in", "not_in", "contains"})

#: Operators legal for the top-level ``context_predicates`` block.
CONTEXT_OPERATORS = frozenset({"==", "!=", ">", ">=", "<", "<=", "in", "not_in"})


def apply_operator(operator: str, target: object, compare: object) -> bool:
    """Apply ``operator`` between a payload-side ``target`` and ``compare``."""
    if operator == "==":
        return target == compare
    if operator == "!=":
        return target != compare
    if operator in {">", ">=", "<", "<="}:
        try:
            t = float(target)  # type: ignore[arg-type]
            c = float(compare)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return False
        if operator == ">":
            return t > c
        if operator == ">=":
            return t >= c
        if operator == "<":
            return t < c
        return t <= c
    if operator == "in":
        try:
            return target in compare  # type: ignore[operator]
        except TypeError:
            return False
    if operator == "not_in":
        try:
            return target not in compare  # type: ignore[operator]
        except TypeError:
            return False
    if operator == "contains":
        try:
            return compare in target  # type: ignore[operator]
        except TypeError:
            return False
    raise ValueError(f"unknown operator: {operator!r}")


# ---------------------------------------------------------------------------
# Sentinel
# ---------------------------------------------------------------------------


class _MissingMarker:
    __slots__ = ()

    def __repr__(self) -> str:
        return "<MISSING_VALUE>"


MISSING_VALUE: _MissingMarker = _MissingMarker()


def _is_mapping(obj: object) -> bool:
    return isinstance(obj, Mapping)


__all__ = [
    "CONTEXT_OPERATORS",
    "MISSING_VALUE",
    "STRUCTURE_OPERATORS",
    "apply_operator",
    "context_lookup",
    "resolve_value",
]
