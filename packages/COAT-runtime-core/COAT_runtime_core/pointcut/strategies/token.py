"""Exact token / sub-token match strategy."""

from __future__ import annotations

from .._text import iter_tokens
from ._base import JSON, NO_MATCH, JoinpointEvent, MatchResult, make_match


def apply(jp: JoinpointEvent, tokens: list[str], context: JSON | None = None) -> MatchResult:
    """Match when *any* token in ``tokens`` appears in the joinpoint payload.

    Token-level joinpoints expose a single ``payload.token``; span-level
    joinpoints expose ``payload.tokens``; other levels fall back to
    whitespace splitting the payload text. Matching is case-sensitive
    because tokens are typically the literal output of a tokenizer.
    """
    if not tokens:
        return NO_MATCH
    wanted = set(tokens)
    matched = [tok for tok in iter_tokens(jp) if tok in wanted]
    if not matched:
        return NO_MATCH
    score = min(1.0, len(set(matched)) / len(wanted))
    return make_match(score, f"token:{sorted(set(matched))!r}")
