"""Tests for :class:`TopKSelector`."""

from __future__ import annotations

from opencoat_runtime_core.coordinator.topk import TopKSelector
from opencoat_runtime_protocol import Concern


def _ranked(n: int) -> list[tuple[Concern, float]]:
    return [(Concern(id=f"c-{i}", name=f"c-{i}"), 1.0 - 0.1 * i) for i in range(n)]


class TestTopKSelector:
    def test_returns_first_k_entries_in_order(self) -> None:
        sel = TopKSelector()
        kept = sel.select(_ranked(5), 3)
        assert [c.id for c, _ in kept] == ["c-0", "c-1", "c-2"]

    def test_k_zero_returns_empty(self) -> None:
        sel = TopKSelector()
        assert sel.select(_ranked(3), 0) == []

    def test_negative_k_returns_empty(self) -> None:
        sel = TopKSelector()
        assert sel.select(_ranked(3), -1) == []

    def test_k_larger_than_input_returns_full_list(self) -> None:
        sel = TopKSelector()
        ranked = _ranked(2)
        assert sel.select(ranked, 10) == ranked

    def test_returns_independent_list(self) -> None:
        sel = TopKSelector()
        ranked = _ranked(3)
        kept = sel.select(ranked, 3)
        assert kept is not ranked
