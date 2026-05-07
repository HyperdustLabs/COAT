"""Budget controller — enforces token / count caps."""

from __future__ import annotations

from COAT_runtime_protocol import Concern

from ..config import RuntimeBudgets


class BudgetController:
    def __init__(self, *, budgets: RuntimeBudgets) -> None:
        self._budgets = budgets

    def enforce(
        self,
        ranked: list[tuple[Concern, float]],
    ) -> list[tuple[Concern, float]]:
        """Drop trailing entries until budgets are satisfied."""
        raise NotImplementedError

    def estimate_tokens(self, concern: Concern) -> int:
        raise NotImplementedError
