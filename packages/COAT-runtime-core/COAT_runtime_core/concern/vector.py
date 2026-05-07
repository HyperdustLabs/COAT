"""Concern Vector builder — v0.1 §17.

A Concern Vector is **not** a dense embedding — it is the sparse
*activation snapshot* of the DCN for the current turn (set of active
concerns + per-concern weights).
"""

from __future__ import annotations

from datetime import UTC, datetime

from COAT_runtime_protocol import ConcernVector
from COAT_runtime_protocol.envelopes import ActiveConcern, VectorBudget

from ..config import RuntimeBudgets


class ConcernVectorBuilder:
    """Assemble a :class:`ConcernVector` from coordinator output."""

    def __init__(self, *, budgets: RuntimeBudgets) -> None:
        self._budgets = budgets

    def build(
        self,
        *,
        turn_id: str,
        agent_session_id: str | None = None,
        active: list[ActiveConcern],
        ts: datetime | None = None,
    ) -> ConcernVector:
        raise NotImplementedError

    def empty(self, turn_id: str) -> ConcernVector:
        return ConcernVector(
            turn_id=turn_id,
            ts=datetime.now(UTC),
            active_concerns=[],
            budget=VectorBudget(
                max_active_concerns=self._budgets.max_active_concerns,
                max_injection_tokens=self._budgets.max_injection_tokens,
            ),
        )
