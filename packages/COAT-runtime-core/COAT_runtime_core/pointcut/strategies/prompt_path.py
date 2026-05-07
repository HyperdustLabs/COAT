"""Prompt-section path strategy (e.g. ``runtime_prompt.verification_rules``)."""

from __future__ import annotations

from ._base import JSON, NO_MATCH, JoinpointEvent, MatchResult, make_match


def apply(jp: JoinpointEvent, paths: list[str], context: JSON | None = None) -> MatchResult:
    """Match if the joinpoint's prompt path matches one of ``paths``.

    Path source: ``payload.path`` if present (prompt_section kind), else
    ``jp.name``. Pattern syntax:

    * ``*``                 — match any non-empty path
    * ``runtime_prompt.*``  — prefix match (trailing wildcard segment)
    * exact string          — equality

    Exact matches are scored 1.0; wildcard hits 0.7 so the matcher can
    prefer specific patterns when both apply.
    """
    if not paths:
        return NO_MATCH
    payload = jp.payload or {}
    raw = payload.get("path")
    target = raw if isinstance(raw, str) else jp.name
    if not target:
        return NO_MATCH
    for pattern in paths:
        if pattern == target:
            return make_match(1.0, f"prompt_path:{target}")
        if pattern == "*":
            return make_match(0.7, f"prompt_path:wildcard:{target}")
        if pattern.endswith(".*"):
            prefix = pattern[:-1]
            if target.startswith(prefix):
                return make_match(0.7, f"prompt_path:prefix:{pattern}")
    return NO_MATCH
