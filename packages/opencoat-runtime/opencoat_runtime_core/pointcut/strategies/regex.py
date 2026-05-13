"""Regex pointcut strategy."""

from __future__ import annotations

import re

from .._text import extract_text
from ._base import JSON, NO_MATCH, JoinpointEvent, MatchResult, make_match


def apply(
    jp: JoinpointEvent,
    pattern: str | re.Pattern[str],
    context: JSON | None = None,
) -> MatchResult:
    """Match if ``pattern`` (compiled or string) matches the payload text.

    The pointcut compiler precompiles ``re.Pattern`` instances at compile
    time; passing a string here is supported for ad-hoc / test use and
    falls back to :func:`re.compile`. Compilation errors propagate.
    """
    text = extract_text(jp)
    if not text:
        return NO_MATCH
    compiled = pattern if isinstance(pattern, re.Pattern) else re.compile(pattern)
    match = compiled.search(text)
    if match is None:
        return NO_MATCH
    return make_match(1.0, f"regex:{compiled.pattern}")
