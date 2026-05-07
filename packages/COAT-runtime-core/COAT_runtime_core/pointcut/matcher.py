"""Pointcut matcher — default :class:`MatcherPlugin` implementation."""

from __future__ import annotations

from COAT_runtime_protocol import JoinpointEvent, Pointcut

from ..ports.matcher import MatcherPlugin, MatchResult
from ..types import JSON


class PointcutMatcher(MatcherPlugin):
    """Composes the per-strategy matchers under :mod:`.strategies`.

    Strategies are AND-combined (every block must succeed) but each
    strategy aggregates its own internal ``OR`` semantics.
    """

    def match(
        self,
        pointcut: Pointcut,
        joinpoint: JoinpointEvent,
        context: JSON | None = None,
    ) -> MatchResult:
        raise NotImplementedError
