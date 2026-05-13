"""Tests for :class:`PriorityRanker`."""

from __future__ import annotations

import pytest
from opencoat_runtime_core.coordinator.priority import PriorityRanker, RankWeights
from opencoat_runtime_protocol import (
    AdviceType,
    Concern,
    ConcernRelationType,
)
from opencoat_runtime_protocol.envelopes import (
    Advice,
    ConcernRelation,
    ConcernSource,
    WeavingPolicy,
)


def _concern(
    cid: str,
    *,
    priority: float = 0.5,
    trust: float | None = None,
    relations: list[ConcernRelation] | None = None,
    advice: Advice | None = None,
) -> Concern:
    source = ConcernSource(origin="system_default", trust=trust) if trust is not None else None
    return Concern(
        id=cid,
        name=cid,
        weaving_policy=WeavingPolicy(priority=priority),
        source=source,
        relations=relations or [],
        advice=advice,
    )


class TestPriorityRanker:
    def test_orders_by_composite_score_descending(self) -> None:
        ranker = PriorityRanker()
        c_high = _concern("c-high", priority=0.9, trust=0.9)
        c_low = _concern("c-low", priority=0.1, trust=0.1)

        ranked = ranker.rank([(c_low, 0.5), (c_high, 0.5)])

        assert [c.id for c, _ in ranked] == ["c-high", "c-low"]
        assert ranked[0][1] > ranked[1][1]

    def test_score_clamped_to_unit_interval(self) -> None:
        ranker = PriorityRanker(
            weights=RankWeights(relevance=10.0, priority=0.0, trust=0.0, history=0.0)
        )
        concern = _concern("c", priority=0.0, trust=0.0)
        ranked = ranker.rank([(concern, 0.5)])
        assert 0.0 <= ranked[0][1] <= 1.0

    def test_zero_relevance_falls_back_to_priority_and_trust(self) -> None:
        ranker = PriorityRanker()
        concern = _concern("c", priority=1.0, trust=1.0)
        [(_, score)] = ranker.rank([(concern, 0.0)])
        assert score > 0.0  # priority + trust contribute

    def test_history_effectiveness_from_context_lifts_score(self) -> None:
        ranker = PriorityRanker()
        concern = _concern("c", priority=0.5, trust=0.5)
        baseline = ranker.rank([(concern, 0.5)])[0][1]
        boosted = ranker.rank(
            [(concern, 0.5)],
            context={"history_effectiveness": {"c": 1.0}},
        )[0][1]
        assert boosted > baseline

    def test_conflict_penalty_from_context_drops_score(self) -> None:
        ranker = PriorityRanker()
        concern = _concern("c", priority=0.5, trust=0.5)
        baseline = ranker.rank([(concern, 0.8)])[0][1]
        penalised = ranker.rank(
            [(concern, 0.8)],
            context={"conflict_penalty": {"c": 1.0}},
        )[0][1]
        assert penalised < baseline

    def test_deterministic_tiebreaker_uses_concern_id(self) -> None:
        ranker = PriorityRanker(
            weights=RankWeights(
                relevance=1.0, priority=0.0, trust=0.0, history=0.0, conflict_penalty=0.0
            )
        )
        a = _concern("c-a", priority=0.5)
        b = _concern("c-b", priority=0.5)
        ranked = ranker.rank([(b, 0.5), (a, 0.5)])
        # equal scores -> sort by id ascending
        assert [c.id for c, _ in ranked] == ["c-a", "c-b"]

    def test_missing_weaving_policy_uses_neutral_priority(self) -> None:
        ranker = PriorityRanker()
        concern = Concern(id="c", name="c")  # no weaving_policy, no source
        [(_, score)] = ranker.rank([(concern, 0.0)])
        # weights default; relevance=history=0, priority=trust=0.5 (neutral)
        w = RankWeights()
        expected = (w.priority * 0.5 + w.trust * 0.5) / w.total()
        assert score == pytest.approx(expected)

    def test_relations_field_is_ignored_by_ranker(self) -> None:
        # The ranker is conflict-blind by design; the resolver handles
        # ``conflicts_with``. This test pins that contract.
        ranker = PriorityRanker()
        rel = ConcernRelation(
            target_concern_id="c-other",
            relation_type=ConcernRelationType.CONFLICTS_WITH,
        )
        concern = _concern("c", priority=0.5, trust=0.5, relations=[rel])
        clean = _concern("c-clean", priority=0.5, trust=0.5)
        ranked = ranker.rank([(concern, 0.7), (clean, 0.7)])
        assert ranked[0][1] == ranked[1][1]

    def test_uses_relevance_weight_when_only_relevance_set(self) -> None:
        # Sanity: a relevance-only ranker echoes the input scores in order.
        ranker = PriorityRanker(
            weights=RankWeights(
                relevance=1.0, priority=0.0, trust=0.0, history=0.0, conflict_penalty=0.0
            )
        )
        a = _concern("c-a")
        b = _concern("c-b")
        ranked = ranker.rank([(a, 0.2), (b, 0.9)])
        assert [c.id for c, _ in ranked] == ["c-b", "c-a"]
        assert ranked[0][1] == pytest.approx(0.9)
        assert ranked[1][1] == pytest.approx(0.2)

    def test_rejects_unknown_advice_type_used_as_proxy_for_real_advice(self) -> None:
        # The ranker should not crash when a concern carries an advice
        # payload (it's irrelevant to ranking but routinely populated).
        ranker = PriorityRanker()
        concern = _concern(
            "c",
            advice=Advice(type=AdviceType.REASONING_GUIDANCE, content="hello"),
        )
        ranked = ranker.rank([(concern, 0.5)])
        assert ranked[0][0].id == "c"
