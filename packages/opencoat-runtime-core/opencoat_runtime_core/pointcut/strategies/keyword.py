"""Keyword (any/all) match strategy."""

from __future__ import annotations

from .._text import extract_text
from ._base import JSON, NO_MATCH, JoinpointEvent, MatchResult, make_match


def apply(
    jp: JoinpointEvent,
    *,
    any_keywords: list[str] | None = None,
    all_keywords: list[str] | None = None,
    case_sensitive: bool = False,
    context: JSON | None = None,
) -> MatchResult:
    """OR over ``any_keywords``, AND over ``all_keywords``.

    Both lists are optional; if neither is supplied the strategy reports
    no match. When both are present they're combined with AND. Score is
    the fraction of supplied keywords found in the payload text (max 1.0).
    """
    if not any_keywords and not all_keywords:
        return NO_MATCH
    text = extract_text(jp)
    if not text:
        return NO_MATCH
    haystack = text if case_sensitive else text.lower()

    def _norm(needle: str) -> str:
        return needle if case_sensitive else needle.lower()

    any_hits = [kw for kw in any_keywords if _norm(kw) in haystack] if any_keywords else None
    all_hits = [kw for kw in all_keywords if _norm(kw) in haystack] if all_keywords else None

    if any_hits is not None and not any_hits:
        return NO_MATCH
    if all_hits is not None and len(all_hits) != len(all_keywords or []):
        return NO_MATCH

    total = len(any_keywords or []) + len(all_keywords or [])
    found = len(any_hits or []) + len(all_hits or [])
    score = found / total if total else 0.0
    return make_match(min(1.0, score), f"keyword:{found}/{total}")
