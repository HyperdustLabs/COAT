"""Claim-shaped strategy — match assertions in the host's draft output.

The host emits claim-bearing joinpoints (typically thought_unit kind) whose
payload carries a ``claims: list[{type, evidence}]`` array. This strategy
filters that list by ``claim_type`` and/or ``evidence_required`` and
matches when at least one claim survives.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from ._base import JSON, NO_MATCH, JoinpointEvent, MatchResult, make_match


def apply(
    jp: JoinpointEvent,
    *,
    claim_type: str | None = None,
    evidence_required: bool | None = None,
    context: JSON | None = None,
) -> MatchResult:
    if claim_type is None and evidence_required is None:
        return NO_MATCH

    payload = jp.payload or {}
    claims_raw = payload.get("claims")
    if not isinstance(claims_raw, Iterable) or isinstance(claims_raw, (str, bytes)):
        return NO_MATCH

    surviving: list[dict] = []
    for claim in claims_raw:
        if not isinstance(claim, Mapping):
            continue
        if claim_type is not None and claim.get("type") != claim_type:
            continue
        if evidence_required is True and not bool(claim.get("evidence")):
            continue
        if evidence_required is False and bool(claim.get("evidence")):
            continue
        surviving.append(dict(claim))

    if not surviving:
        return NO_MATCH
    return make_match(1.0, f"claim:matched={len(surviving)}")
