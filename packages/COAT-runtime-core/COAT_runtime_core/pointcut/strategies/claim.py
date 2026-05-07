"""Claim-shaped strategy — match assertions in the host's draft output."""

from __future__ import annotations

from ._base import JSON, JoinpointEvent, MatchResult


def apply(
    jp: JoinpointEvent,
    *,
    claim_type: str | None = None,
    evidence_required: bool | None = None,
    context: JSON | None = None,
) -> MatchResult:
    raise NotImplementedError
