"""Activation-history strategy.

Concrete predicates (``activated_in_last_n_turns``, ``satisfied_ratio_above``,
…) are added in M2 once the activation log has a stable shape.
"""

from __future__ import annotations

from ._base import JSON, JoinpointEvent, MatchResult


def apply(jp: JoinpointEvent, predicate: dict, context: JSON | None = None) -> MatchResult:
    raise NotImplementedError
