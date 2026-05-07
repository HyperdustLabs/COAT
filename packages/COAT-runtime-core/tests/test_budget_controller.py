"""Tests for :class:`BudgetController`."""

from __future__ import annotations

from COAT_runtime_core.config import RuntimeBudgets
from COAT_runtime_core.coordinator.budget import BudgetController
from COAT_runtime_protocol import AdviceType, Concern
from COAT_runtime_protocol.envelopes import Advice


def _concern(cid: str, *, content: str = "", rationale: str | None = None) -> Concern:
    advice = (
        Advice(
            type=AdviceType.REASONING_GUIDANCE,
            content=content or "noop",
            rationale=rationale,
        )
        if content or rationale
        else None
    )
    return Concern(id=cid, name=cid, advice=advice)


class TestBudgetController:
    def test_count_cap_drops_trailing_entries(self) -> None:
        ctrl = BudgetController(budgets=RuntimeBudgets(max_active_concerns=2))
        ranked = [(_concern(f"c-{i}"), 1.0 - 0.1 * i) for i in range(5)]
        kept = ctrl.enforce(ranked)
        assert [c.id for c, _ in kept] == ["c-0", "c-1"]

    def test_token_cap_drops_concerns_when_exceeded(self) -> None:
        # Each "x" * 40 -> ~10 tokens at 4 chars/token. Budget=15 tokens
        # admits the first concern (10 tokens) and rejects the next.
        ctrl = BudgetController(
            budgets=RuntimeBudgets(max_active_concerns=10, max_injection_tokens=15)
        )
        ranked = [(_concern(f"c-{i}", content="x" * 40), 1.0 - 0.1 * i) for i in range(3)]
        kept = ctrl.enforce(ranked)
        assert [c.id for c, _ in kept] == ["c-0"]

    def test_first_oversized_concern_is_always_admitted(self) -> None:
        # A single concern bigger than the whole budget would otherwise
        # drop the entire vector — always let the top entry through.
        ctrl = BudgetController(
            budgets=RuntimeBudgets(max_active_concerns=10, max_injection_tokens=5)
        )
        ranked = [(_concern("c-big", content="x" * 200), 0.9)]
        kept = ctrl.enforce(ranked)
        assert len(kept) == 1
        assert kept[0][0].id == "c-big"

    def test_empty_input_returns_empty(self) -> None:
        ctrl = BudgetController(budgets=RuntimeBudgets())
        assert ctrl.enforce([]) == []

    def test_estimate_tokens_with_no_advice_is_zero(self) -> None:
        ctrl = BudgetController(budgets=RuntimeBudgets())
        assert ctrl.estimate_tokens(_concern("c")) == 0

    def test_estimate_tokens_capped_by_advice_max_tokens(self) -> None:
        ctrl = BudgetController(budgets=RuntimeBudgets())
        concern = Concern(
            id="c",
            name="c",
            advice=Advice(
                type=AdviceType.REASONING_GUIDANCE,
                content="x" * 1000,
                max_tokens=10,
            ),
        )
        assert ctrl.estimate_tokens(concern) == 10

    def test_rationale_counted_against_budget(self) -> None:
        ctrl = BudgetController(budgets=RuntimeBudgets())
        no_rationale = Concern(
            id="a",
            name="a",
            advice=Advice(type=AdviceType.REASONING_GUIDANCE, content="hello"),
        )
        with_rationale = Concern(
            id="b",
            name="b",
            advice=Advice(
                type=AdviceType.REASONING_GUIDANCE,
                content="hello",
                rationale="x" * 20,
            ),
        )
        assert ctrl.estimate_tokens(with_rationale) > ctrl.estimate_tokens(no_rationale)
