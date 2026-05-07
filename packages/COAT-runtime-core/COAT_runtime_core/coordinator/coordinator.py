"""Concern Coordinator — v0.1 §20.7.

Builds the per-turn :class:`ConcernVector` by orchestrating top-K selection,
priority ranking, and budget enforcement.
"""

from __future__ import annotations

from COAT_runtime_protocol import Concern, ConcernVector, JoinpointEvent

from ..concern.vector import ConcernVectorBuilder
from ..config import RuntimeBudgets
from .budget import BudgetController
from .priority import PriorityRanker
from .topk import TopKSelector


class ConcernCoordinator:
    def __init__(
        self,
        *,
        budgets: RuntimeBudgets,
        vector_builder: ConcernVectorBuilder | None = None,
        topk: TopKSelector | None = None,
        priority: PriorityRanker | None = None,
        budget_controller: BudgetController | None = None,
    ) -> None:
        self._budgets = budgets
        self._vector_builder = vector_builder or ConcernVectorBuilder(budgets=budgets)
        self._topk = topk or TopKSelector()
        self._priority = priority or PriorityRanker()
        self._budget = budget_controller or BudgetController(budgets=budgets)

    def coordinate(
        self,
        *,
        turn_id: str,
        candidates: list[tuple[Concern, float]],
        joinpoint: JoinpointEvent,
        context: dict | None = None,
    ) -> ConcernVector:
        raise NotImplementedError
