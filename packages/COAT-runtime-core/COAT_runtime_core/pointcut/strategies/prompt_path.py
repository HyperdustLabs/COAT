"""Prompt-section path strategy (e.g. ``runtime_prompt.verification_rules``)."""

from __future__ import annotations

from ._base import JSON, JoinpointEvent, MatchResult


def apply(jp: JoinpointEvent, paths: list[str], context: JSON | None = None) -> MatchResult:
    """Match if the joinpoint's prompt path matches one of ``paths``.

    Supports trailing ``*`` wildcards (e.g. ``runtime_prompt.*``).
    """
    raise NotImplementedError
