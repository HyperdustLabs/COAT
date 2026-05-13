"""Semantic-intent strategy.

M1 ships a deliberate **stub**: it falls back to case-insensitive substring
match against the joinpoint's text payload. The full embedder + cosine
threshold implementation lands in M2 alongside :mod:`opencoat_runtime_storage.vector`
and :mod:`opencoat_runtime_llm.embedder`.

The ``threshold`` parameter is accepted for forward-compatibility but
ignored at M1; once embeddings are wired in, the M2 implementation will
drop the substring fallback in favour of cosine ≥ ``threshold``.
"""

from __future__ import annotations

from .._text import extract_text
from ._base import JSON, NO_MATCH, JoinpointEvent, MatchResult, make_match


def apply(
    jp: JoinpointEvent,
    semantic_intent: str,
    *,
    threshold: float = 0.7,
    context: JSON | None = None,
) -> MatchResult:
    if not semantic_intent.strip():
        return NO_MATCH
    text = extract_text(jp)
    if not text:
        return NO_MATCH
    if semantic_intent.lower() in text.lower():
        return make_match(1.0, f"semantic:stub_substring:{semantic_intent!r}")
    return NO_MATCH
