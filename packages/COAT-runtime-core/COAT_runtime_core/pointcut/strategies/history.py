"""Activation-history strategy.

The history block is intentionally freeform in the schema (M2 will
formalise it). M1 implements a small, useful subset whose semantics are
clearly bounded:

* ``activated_in_last_n_turns: int``
    matches when ``context['turns_since_activation']`` is present and
    less than or equal to the threshold.
* ``min_activations: int``
    matches when ``context['total_activations']`` is at least the threshold.
* ``min_satisfied_ratio: float``
    matches when ``context['satisfied_ratio']`` is at least the threshold.

Multiple keys are AND-combined. Unknown keys are treated as failed
constraints so misspellings surface as "no match" rather than silently
disappearing.
"""

from __future__ import annotations

from collections.abc import Mapping

from .._context import MISSING_VALUE, context_lookup
from ._base import JSON, NO_MATCH, JoinpointEvent, MatchResult, make_match

_SUPPORTED = {
    "activated_in_last_n_turns",
    "min_activations",
    "min_satisfied_ratio",
}


def apply(
    jp: JoinpointEvent, predicate: Mapping[str, object], context: JSON | None = None
) -> MatchResult:
    if not predicate:
        return NO_MATCH
    unknown = set(predicate) - _SUPPORTED
    if unknown:
        return NO_MATCH

    if "activated_in_last_n_turns" in predicate:
        n = predicate["activated_in_last_n_turns"]
        ctx_value = context_lookup(context, "turns_since_activation")
        if ctx_value is MISSING_VALUE:
            return NO_MATCH
        try:
            if float(ctx_value) > float(n):  # type: ignore[arg-type]
                return NO_MATCH
        except (TypeError, ValueError):
            return NO_MATCH

    if "min_activations" in predicate:
        n = predicate["min_activations"]
        ctx_value = context_lookup(context, "total_activations")
        if ctx_value is MISSING_VALUE:
            return NO_MATCH
        try:
            if float(ctx_value) < float(n):  # type: ignore[arg-type]
                return NO_MATCH
        except (TypeError, ValueError):
            return NO_MATCH

    if "min_satisfied_ratio" in predicate:
        ratio = predicate["min_satisfied_ratio"]
        ctx_value = context_lookup(context, "satisfied_ratio")
        if ctx_value is MISSING_VALUE:
            return NO_MATCH
        try:
            if float(ctx_value) < float(ratio):  # type: ignore[arg-type]
                return NO_MATCH
        except (TypeError, ValueError):
            return NO_MATCH

    return make_match(1.0, f"history:{sorted(predicate)}")
