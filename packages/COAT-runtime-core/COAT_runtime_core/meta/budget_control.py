"""Meta concern: per-turn budget overrides."""

from __future__ import annotations

from ..config import RuntimeBudgets


class BudgetControl:
    def adjust(self, base: RuntimeBudgets, *, context: dict | None = None) -> RuntimeBudgets:
        raise NotImplementedError
