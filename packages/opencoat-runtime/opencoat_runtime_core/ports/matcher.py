"""Pointcut matcher plugin port.

The default matcher lives in :mod:`opencoat_runtime_core.pointcut.matcher`. Third
parties can drop in alternative matchers (e.g. embedding-only, rules-engine)
that implement this protocol.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from opencoat_runtime_protocol import JoinpointEvent, Pointcut

from ..types import JSON, UnitFloat


@dataclass(frozen=True)
class MatchResult:
    matched: bool
    score: UnitFloat = 0.0
    reasons: tuple[str, ...] = ()


@runtime_checkable
class MatcherPlugin(Protocol):
    """Stateless pointcut matcher."""

    def match(
        self,
        pointcut: Pointcut,
        joinpoint: JoinpointEvent,
        context: JSON | None = None,
    ) -> MatchResult: ...
