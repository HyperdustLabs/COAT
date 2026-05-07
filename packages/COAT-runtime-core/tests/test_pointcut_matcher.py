"""End-to-end matcher tests covering the full pipeline.

joinpoint filter + match block + context predicates AND-combined.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from COAT_runtime_core.pointcut import PointcutMatcher
from COAT_runtime_core.ports.matcher import MatcherPlugin
from COAT_runtime_protocol import (
    ConfidenceMatch,
    ContextPredicate,
    JoinpointEvent,
    JoinpointSelector,
    Pointcut,
    PointcutMatch,
    RiskMatch,
    StructureMatch,
)


def _jp(
    name: str = "before_response",
    *,
    level: int = 1,
    payload: dict[str, Any] | None = None,
) -> JoinpointEvent:
    return JoinpointEvent(
        id=f"jp-{name}",
        level=level,
        name=name,
        host="test-host",
        ts=datetime(2026, 1, 1, tzinfo=UTC),
        payload=payload,
    )


# ---------------------------------------------------------------------------
# Protocol shape
# ---------------------------------------------------------------------------


def test_implements_matcher_plugin_protocol() -> None:
    assert isinstance(PointcutMatcher(), MatcherPlugin)


# ---------------------------------------------------------------------------
# Joinpoint filter only
# ---------------------------------------------------------------------------


class TestJoinpointFilter:
    def test_filter_passes_when_empty(self) -> None:
        result = PointcutMatcher().match(Pointcut(), _jp())
        assert result.matched
        assert "joinpoint_filter" in result.reasons

    def test_filter_by_string_name(self) -> None:
        pc = Pointcut(joinpoints=["before_response"])
        assert PointcutMatcher().match(pc, _jp("before_response")).matched
        assert not PointcutMatcher().match(pc, _jp("after_response")).matched

    def test_filter_by_selector_level(self) -> None:
        pc = Pointcut(joinpoints=[JoinpointSelector(level="lifecycle")])
        assert PointcutMatcher().match(pc, _jp(level=1)).matched
        assert not PointcutMatcher().match(pc, _jp(level=4)).matched

    def test_filter_by_selector_path(self) -> None:
        pc = Pointcut(
            joinpoints=[
                JoinpointSelector(level="prompt_section", path="runtime_prompt.verification_rules")
            ]
        )
        ok = _jp(
            "runtime_prompt.verification_rules",
            level=3,
            payload={
                "kind": "prompt_section",
                "path": "runtime_prompt.verification_rules",
            },
        )
        miss = _jp(
            "runtime_prompt.tool_instructions",
            level=3,
            payload={"kind": "prompt_section", "path": "runtime_prompt.tool_instructions"},
        )
        assert PointcutMatcher().match(pc, ok).matched
        assert not PointcutMatcher().match(pc, miss).matched

    def test_filter_by_selector_match_keywords(self) -> None:
        pc = Pointcut(joinpoints=[JoinpointSelector(level="message", match=["refund"])])
        ok = _jp(
            "user_message",
            level=2,
            payload={"kind": "message", "raw_text": "please refund my order"},
        )
        miss = _jp("user_message", level=2, payload={"kind": "message", "raw_text": "ship it"})
        assert PointcutMatcher().match(pc, ok).matched
        assert not PointcutMatcher().match(pc, miss).matched


# ---------------------------------------------------------------------------
# Inert match block (fail closed) — regression Codex PR #2 review
# ---------------------------------------------------------------------------


class TestInertMatchBlock:
    def test_empty_keyword_lists_fail_closed_without_context(self) -> None:
        pc = Pointcut(
            joinpoints=["before_response"],
            match=PointcutMatch(any_keywords=[], all_keywords=[]),
        )
        result = PointcutMatcher().match(pc, _jp("before_response"))
        assert not result.matched
        assert "miss:inert_match_block" in result.reasons

    def test_inert_match_allowed_when_context_predicates_present(self) -> None:
        pc = Pointcut(
            joinpoints=["before_response"],
            match=PointcutMatch(any_keywords=[], all_keywords=[]),
            context_predicates=[
                ContextPredicate(key="tier", op="==", value="gold"),
            ],
        )
        assert PointcutMatcher().match(pc, _jp("before_response"), context={"tier": "gold"}).matched

    def test_whitespace_only_semantic_intent_is_inert(self) -> None:
        pc = Pointcut(
            joinpoints=["before_response"],
            match=PointcutMatch(semantic_intent="   "),
        )
        result = PointcutMatcher().match(pc, _jp("before_response"))
        assert not result.matched
        assert "miss:inert_match_block" in result.reasons


# ---------------------------------------------------------------------------
# Match block
# ---------------------------------------------------------------------------


class TestMatchBlock:
    def test_keyword_and_regex_combine_with_and(self) -> None:
        pc = Pointcut(
            match=PointcutMatch(any_keywords=["refund"], regex=r"#\d+"),
        )
        ok = _jp(payload={"kind": "message", "raw_text": "please refund order #99"})
        miss = _jp(payload={"kind": "message", "raw_text": "please refund my order"})
        assert PointcutMatcher().match(pc, ok).matched
        assert not PointcutMatcher().match(pc, miss).matched

    def test_structure_via_value_ref(self) -> None:
        pc = Pointcut(
            match=PointcutMatch(
                structure=StructureMatch(
                    field="tool_call.arguments.amount",
                    operator=">",
                    value_ref="risk_budget.max_amount",
                )
            )
        )
        jp = _jp(
            "tool_call",
            level=6,
            payload={
                "kind": "structure_field",
                "tool_call": {"arguments": {"amount": 5000}},
            },
        )
        result = PointcutMatcher().match(pc, jp, context={"risk_budget": {"max_amount": 1000}})
        assert result.matched

    def test_confidence_below_threshold(self) -> None:
        pc = Pointcut(match=PointcutMatch(confidence=ConfidenceMatch(op="<", threshold=0.5)))
        jp = _jp()
        assert PointcutMatcher().match(pc, jp, context={"confidence": 0.3}).matched
        assert not PointcutMatcher().match(pc, jp, context={"confidence": 0.9}).matched

    def test_risk_threshold(self) -> None:
        pc = Pointcut(match=PointcutMatch(risk=RiskMatch(op=">=", level="high")))
        jp = _jp()
        assert PointcutMatcher().match(pc, jp, context={"risk_level": "critical"}).matched
        assert not PointcutMatcher().match(pc, jp, context={"risk_level": "low"}).matched

    def test_history_predicate(self) -> None:
        pc = Pointcut(match=PointcutMatch(history={"min_activations": 2}))
        jp = _jp()
        assert PointcutMatcher().match(pc, jp, context={"total_activations": 5}).matched

    def test_score_is_minimum_across_strategies(self) -> None:
        pc = Pointcut(match=PointcutMatch(any_keywords=["alpha", "beta", "gamma", "delta"]))
        jp = _jp(payload={"kind": "message", "raw_text": "alpha"})
        result = PointcutMatcher().match(pc, jp)
        assert result.matched
        assert result.score == 0.25  # 1/4


# ---------------------------------------------------------------------------
# Context predicates
# ---------------------------------------------------------------------------


class TestContextPredicates:
    def test_predicate_passes(self) -> None:
        pc = Pointcut(
            context_predicates=[
                ContextPredicate(key="tenant_tier", op="==", value="gold"),
            ]
        )
        assert PointcutMatcher().match(pc, _jp(), context={"tenant_tier": "gold"}).matched

    def test_predicate_value_ref(self) -> None:
        pc = Pointcut(
            context_predicates=[
                ContextPredicate(key="amount", op="<", value_ref="budget.cap"),
            ]
        )
        result = PointcutMatcher().match(
            pc,
            _jp(),
            context={"amount": 200, "budget": {"cap": 1000}},
        )
        assert result.matched

    def test_predicate_key_missing(self) -> None:
        pc = Pointcut(context_predicates=[ContextPredicate(key="missing", op="==", value=1)])
        result = PointcutMatcher().match(pc, _jp(), context={})
        assert not result.matched
        assert "miss:context_key:missing" in result.reasons


# ---------------------------------------------------------------------------
# Combination
# ---------------------------------------------------------------------------


def test_full_pipeline_filter_match_context() -> None:
    pc = Pointcut(
        joinpoints=["before_tool_call"],
        match=PointcutMatch(
            structure=StructureMatch(field="tool_call.arguments.amount", operator=">", value=1000),
            risk=RiskMatch(op=">=", level="medium"),
        ),
        context_predicates=[
            ContextPredicate(key="tenant_tier", op="!=", value="free"),
        ],
    )
    jp = _jp(
        "before_tool_call",
        level=1,
        payload={
            "kind": "lifecycle",
            "tool_call": {"arguments": {"amount": 5000}},
        },
    )
    context = {"risk_level": "high", "tenant_tier": "gold"}
    result = PointcutMatcher().match(pc, jp, context=context)
    assert result.matched
