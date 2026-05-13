"""Per-strategy tests for the 12 pointcut strategies.

Each strategy lives in its own module under
:mod:`opencoat_runtime_core.pointcut.strategies`. These tests exercise both
happy paths and the most common edge cases (missing payload, wrong type,
boundary scores).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from opencoat_runtime_core.pointcut.strategies import (
    claim,
    confidence,
    history,
    keyword,
    lifecycle,
    prompt_path,
    risk,
    role,
    semantic,
    structure,
    token,
)
from opencoat_runtime_core.pointcut.strategies import (
    regex as regex_strategy,
)
from opencoat_runtime_protocol import JoinpointEvent


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
# lifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    def test_match_by_payload_stage(self) -> None:
        jp = _jp("before_response", payload={"kind": "lifecycle", "stage": "before_response"})
        result = lifecycle.apply(jp, ["before_response", "after_response"])
        assert result.matched
        assert result.score == 1.0

    def test_match_by_name_when_payload_missing(self) -> None:
        jp = _jp("on_user_input", payload=None)
        result = lifecycle.apply(jp, ["on_user_input"])
        assert result.matched

    def test_no_match(self) -> None:
        jp = _jp("before_response", payload={"kind": "lifecycle", "stage": "before_response"})
        assert not lifecycle.apply(jp, ["before_planning"]).matched

    def test_empty_stages_means_no_match(self) -> None:
        jp = _jp("before_response", payload={"kind": "lifecycle", "stage": "before_response"})
        assert not lifecycle.apply(jp, []).matched


# ---------------------------------------------------------------------------
# role
# ---------------------------------------------------------------------------


class TestRole:
    def test_match_user_role(self) -> None:
        jp = _jp("user_message", level=2, payload={"kind": "message", "role": "user"})
        assert role.apply(jp, ["user", "assistant"]).matched

    def test_no_payload_no_match(self) -> None:
        jp = _jp("user_message", level=2, payload=None)
        assert not role.apply(jp, ["user"]).matched

    def test_role_not_string_no_match(self) -> None:
        jp = _jp("user_message", level=2, payload={"kind": "message", "role": 123})
        assert not role.apply(jp, ["user"]).matched


# ---------------------------------------------------------------------------
# prompt_path
# ---------------------------------------------------------------------------


class TestPromptPath:
    def test_exact_match_scores_high(self) -> None:
        jp = _jp(
            "runtime_prompt.verification_rules",
            level=3,
            payload={"kind": "prompt_section", "path": "runtime_prompt.verification_rules"},
        )
        result = prompt_path.apply(jp, ["runtime_prompt.verification_rules"])
        assert result.matched
        assert result.score == 1.0

    def test_prefix_wildcard(self) -> None:
        jp = _jp(
            "runtime_prompt.verification_rules",
            level=3,
            payload={"kind": "prompt_section", "path": "runtime_prompt.verification_rules"},
        )
        result = prompt_path.apply(jp, ["runtime_prompt.*"])
        assert result.matched
        assert result.score == 0.7

    def test_global_wildcard(self) -> None:
        jp = _jp("anything", level=3, payload={"kind": "prompt_section", "path": "x.y"})
        assert prompt_path.apply(jp, ["*"]).matched

    def test_no_match(self) -> None:
        jp = _jp(
            "runtime_prompt.verification_rules",
            level=3,
            payload={"kind": "prompt_section", "path": "runtime_prompt.verification_rules"},
        )
        assert not prompt_path.apply(jp, ["system_prompt.rules"]).matched


# ---------------------------------------------------------------------------
# keyword
# ---------------------------------------------------------------------------


class TestKeyword:
    def test_any_keywords_or_semantics(self) -> None:
        jp = _jp(
            "user_message",
            payload={"kind": "message", "raw_text": "Please refund my order"},
        )
        result = keyword.apply(jp, any_keywords=["refund", "ship"])
        assert result.matched
        assert "1/2" in next(r for r in result.reasons if "keyword:" in r)

    def test_all_keywords_and_semantics(self) -> None:
        jp = _jp(
            payload={"kind": "message", "raw_text": "Please refund order #12 immediately"},
        )
        assert keyword.apply(jp, all_keywords=["refund", "order"]).matched
        assert not keyword.apply(jp, all_keywords=["refund", "subscription"]).matched

    def test_case_insensitive_by_default(self) -> None:
        jp = _jp(payload={"kind": "message", "raw_text": "REFUND requested"})
        assert keyword.apply(jp, any_keywords=["refund"]).matched

    def test_case_sensitive_opt_in(self) -> None:
        jp = _jp(payload={"kind": "message", "raw_text": "REFUND requested"})
        assert not keyword.apply(jp, any_keywords=["refund"], case_sensitive=True).matched

    def test_no_keywords_no_match(self) -> None:
        jp = _jp(payload={"kind": "message", "raw_text": "x"})
        assert not keyword.apply(jp).matched


# ---------------------------------------------------------------------------
# regex
# ---------------------------------------------------------------------------


class TestRegex:
    def test_string_pattern(self) -> None:
        jp = _jp(payload={"kind": "message", "raw_text": "order #1234 placed"})
        assert regex_strategy.apply(jp, r"#\d+").matched

    def test_compiled_pattern(self) -> None:
        jp = _jp(payload={"kind": "message", "raw_text": "abc"})
        assert regex_strategy.apply(jp, re.compile(r"a.c")).matched

    def test_no_match(self) -> None:
        jp = _jp(payload={"kind": "message", "raw_text": "hello"})
        assert not regex_strategy.apply(jp, r"\d+").matched

    def test_empty_text(self) -> None:
        jp = _jp(payload=None)
        assert not regex_strategy.apply(jp, r".*").matched


# ---------------------------------------------------------------------------
# semantic (M1 stub: substring)
# ---------------------------------------------------------------------------


class TestSemanticStub:
    def test_substring_match(self) -> None:
        jp = _jp(payload={"kind": "message", "raw_text": "I want a refund please"})
        assert semantic.apply(jp, "refund").matched

    def test_no_match(self) -> None:
        jp = _jp(payload={"kind": "message", "raw_text": "ship it"})
        assert not semantic.apply(jp, "refund").matched

    def test_empty_intent(self) -> None:
        jp = _jp(payload={"kind": "message", "raw_text": "anything"})
        assert not semantic.apply(jp, "   ").matched


# ---------------------------------------------------------------------------
# structure
# ---------------------------------------------------------------------------


class TestStructure:
    def test_numeric_gt(self) -> None:
        jp = _jp(
            "tool_call",
            level=6,
            payload={"kind": "structure_field", "tool_call": {"arguments": {"amount": 5000}}},
        )
        assert structure.apply(
            jp, field="tool_call.arguments.amount", operator=">", value=1000
        ).matched

    def test_value_ref_via_context(self) -> None:
        jp = _jp(
            level=6,
            payload={"kind": "structure_field", "tool_call": {"arguments": {"amount": 500}}},
        )
        result = structure.apply(
            jp,
            field="tool_call.arguments.amount",
            operator="<",
            value_ref="risk_budget.max_amount",
            context={"risk_budget": {"max_amount": 1000}},
        )
        assert result.matched

    def test_in_operator(self) -> None:
        jp = _jp(level=6, payload={"kind": "structure_field", "tier": "gold"})
        assert structure.apply(jp, field="tier", operator="in", value=["gold", "platinum"]).matched

    def test_contains_operator(self) -> None:
        jp = _jp(level=6, payload={"kind": "structure_field", "tags": ["a", "b", "c"]})
        assert structure.apply(jp, field="tags", operator="contains", value="b").matched

    def test_missing_field_no_match(self) -> None:
        jp = _jp(payload={"kind": "structure_field"})
        assert not structure.apply(jp, field="missing", operator="==", value=1).matched


# ---------------------------------------------------------------------------
# token
# ---------------------------------------------------------------------------


class TestToken:
    def test_token_payload_exact(self) -> None:
        jp = _jp("token", level=5, payload={"kind": "token", "token": "stop"})
        assert token.apply(jp, ["stop", "halt"]).matched

    def test_span_tokens(self) -> None:
        jp = _jp(
            level=4,
            payload={"kind": "span", "span_id": "s1", "tokens": ["please", "refund"]},
        )
        assert token.apply(jp, ["refund"]).matched

    def test_text_fallback(self) -> None:
        jp = _jp(payload={"kind": "message", "raw_text": "alpha beta gamma"})
        assert token.apply(jp, ["beta"]).matched

    def test_no_match(self) -> None:
        jp = _jp(payload={"kind": "token", "token": "go"})
        assert not token.apply(jp, ["stop"]).matched


# ---------------------------------------------------------------------------
# claim
# ---------------------------------------------------------------------------


class TestClaim:
    def test_match_by_type(self) -> None:
        jp = _jp(
            level=7,
            payload={
                "kind": "thought_unit",
                "unit_type": "verification_claim",
                "claims": [{"type": "factual", "evidence": True}],
            },
        )
        assert claim.apply(jp, claim_type="factual").matched

    def test_evidence_required(self) -> None:
        jp = _jp(
            level=7,
            payload={
                "kind": "thought_unit",
                "unit_type": "verification_claim",
                "claims": [{"type": "factual", "evidence": False}],
            },
        )
        assert not claim.apply(jp, claim_type="factual", evidence_required=True).matched
        assert claim.apply(jp, claim_type="factual", evidence_required=False).matched

    def test_no_predicate_no_match(self) -> None:
        jp = _jp(payload={"kind": "thought_unit", "claims": []})
        assert not claim.apply(jp).matched


# ---------------------------------------------------------------------------
# confidence
# ---------------------------------------------------------------------------


class TestConfidence:
    def test_context_confidence_below(self) -> None:
        jp = _jp()
        assert confidence.apply(jp, op="<", threshold=0.5, context={"confidence": 0.3}).matched

    def test_payload_fallback(self) -> None:
        jp = _jp(payload={"kind": "message", "raw_text": "x", "confidence": 0.9})
        assert confidence.apply(jp, op=">=", threshold=0.8).matched

    def test_missing_no_match(self) -> None:
        jp = _jp()
        assert not confidence.apply(jp, op=">", threshold=0.5).matched


# ---------------------------------------------------------------------------
# risk
# ---------------------------------------------------------------------------


class TestRisk:
    def test_ge_critical(self) -> None:
        jp = _jp()
        assert risk.apply(jp, op=">=", level="high", context={"risk_level": "critical"}).matched

    def test_eq_low(self) -> None:
        jp = _jp(payload={"kind": "message", "risk_level": "low"})
        assert risk.apply(jp, op="==", level="low").matched
        assert not risk.apply(jp, op="==", level="medium").matched

    def test_unknown_value_no_match(self) -> None:
        jp = _jp()
        assert not risk.apply(jp, op="==", level="high", context={"risk_level": "extreme"}).matched


# ---------------------------------------------------------------------------
# history
# ---------------------------------------------------------------------------


class TestHistory:
    def test_activated_in_last_n_turns(self) -> None:
        jp = _jp()
        assert history.apply(
            jp, {"activated_in_last_n_turns": 5}, context={"turns_since_activation": 2}
        ).matched

    def test_min_activations(self) -> None:
        jp = _jp()
        assert history.apply(jp, {"min_activations": 3}, context={"total_activations": 10}).matched
        assert not history.apply(
            jp, {"min_activations": 3}, context={"total_activations": 1}
        ).matched

    def test_min_satisfied_ratio(self) -> None:
        jp = _jp()
        assert history.apply(
            jp, {"min_satisfied_ratio": 0.5}, context={"satisfied_ratio": 0.8}
        ).matched

    def test_unknown_key_no_match(self) -> None:
        jp = _jp()
        assert not history.apply(
            jp, {"weird_key": 1}, context={"turns_since_activation": 0}
        ).matched

    def test_missing_context_no_match(self) -> None:
        jp = _jp()
        assert not history.apply(jp, {"activated_in_last_n_turns": 1}).matched

    def test_empty_predicate_no_match(self) -> None:
        jp = _jp()
        assert not history.apply(jp, {}).matched
