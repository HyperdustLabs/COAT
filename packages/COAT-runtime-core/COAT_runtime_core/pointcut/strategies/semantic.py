"""Semantic-intent strategy.

Default implementation in M2 will use either an embedder + cosine threshold
or a small LLM judge call. M0 keeps the signature only.
"""

from __future__ import annotations

from ._base import JSON, JoinpointEvent, MatchResult


def apply(
    jp: JoinpointEvent,
    semantic_intent: str,
    *,
    threshold: float = 0.7,
    context: JSON | None = None,
) -> MatchResult:
    raise NotImplementedError
