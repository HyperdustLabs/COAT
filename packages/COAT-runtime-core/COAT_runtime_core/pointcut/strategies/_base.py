"""Shared helpers for the per-strategy matchers."""

from __future__ import annotations

from COAT_runtime_protocol import JoinpointEvent

from ...ports.matcher import MatchResult
from ...types import JSON

NO_MATCH = MatchResult(matched=False, score=0.0, reasons=())


def make_match(score: float, *reasons: str) -> MatchResult:
    return MatchResult(matched=True, score=score, reasons=tuple(reasons))


__all__ = ["JSON", "NO_MATCH", "JoinpointEvent", "MatchResult", "make_match"]
