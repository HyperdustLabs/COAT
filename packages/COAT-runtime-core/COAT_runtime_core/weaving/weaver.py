"""Concern Weaver — builds the per-turn :class:`ConcernInjection` payload."""

from __future__ import annotations

from COAT_runtime_protocol import Advice, Concern, ConcernInjection, ConcernVector

from ..config import RuntimeBudgets


class ConcernWeaver:
    """Compose advice + weaving policies into a single Concern Injection.

    The weaver enforces token / count budgets and is the only module allowed
    to materialize the host-consumable :class:`ConcernInjection` shape.
    """

    def __init__(self, *, budgets: RuntimeBudgets) -> None:
        self._budgets = budgets

    def build(
        self,
        *,
        turn_id: str,
        vector: ConcernVector,
        concerns: dict[str, Concern],
        advices: dict[str, Advice],
    ) -> ConcernInjection:
        raise NotImplementedError
