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

    def test_oversized_higher_ranked_concern_does_not_yield_to_smaller_lower_ranked(
        self,
    ) -> None:
        # Regression for the cutoff-vs-binpack contract:
        # ``c-mid`` cannot fit in the remaining budget, so the controller
        # must STOP — admitting the smaller ``c-low`` in its place would
        # invert the ranker's order. After ``c-high`` (8 tokens) is in,
        # 8 + 50 > 20, so ``c-mid`` is dropped. ``c-low`` would fit
        # individually (8 + 5 = 13) but must NOT be promoted.
        ctrl = BudgetController(
            budgets=RuntimeBudgets(max_active_concerns=10, max_injection_tokens=20)
        )
        c_high = _concern("c-high", content="x" * 32)  # ~8 tokens
        c_mid = _concern("c-mid", content="x" * 200)  # ~50 tokens
        c_low = _concern("c-low", content="x" * 20)  # ~5 tokens
        kept = ctrl.enforce([(c_high, 0.9), (c_mid, 0.7), (c_low, 0.3)])
        assert [c.id for c, _ in kept] == ["c-high"]

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
