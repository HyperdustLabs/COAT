"""Structured-field comparison strategy.

Looks up ``field`` in the joinpoint payload (dotted path), then applies one of:
``== / != / > / >= / < / <= / in / not_in / contains``. ``value_ref`` reads
the comparison value from ``context`` instead of being literal.
"""

from __future__ import annotations

from ._base import JSON, JoinpointEvent, MatchResult


def apply(
    jp: JoinpointEvent,
    *,
    field: str,
    operator: str,
    value: object | None = None,
    value_ref: str | None = None,
    context: JSON | None = None,
) -> MatchResult:
    raise NotImplementedError
