"""Tests for :class:`ConcernBuilder` (§20.3 MVP)."""

from __future__ import annotations

from opencoat_runtime_core.concern.builder import ConcernBuilder
from opencoat_runtime_core.concern.builder_templates import resolve_activation
from opencoat_runtime_protocol import Advice, AdviceType, Concern, Pointcut
from opencoat_runtime_protocol.envelopes import ConcernSource, PointcutMatch
from opencoat_runtime_storage.memory import MemoryConcernStore


def _candidate(
    *,
    generated_type: str = "user_constraint",
    tags: list[str] | None = None,
    origin: str = "user_input",
) -> Concern:
    return Concern(
        id="c-test-builder",
        name="Keep answers brief",
        description="Responses must stay under three sentences.",
        generated_type=generated_type,
        generated_tags=tags or ["brief", "concise"],
        source=ConcernSource(origin=origin, ref="r1"),
    )


def test_resolve_activation_tool_policy() -> None:
    c = _candidate(generated_type="tool_policy", tags=["shell"])
    resolved = resolve_activation(c)
    assert resolved.advice_type == AdviceType.TOOL_GUARD
    assert "before_tool_call" in resolved.joinpoints


def test_enrich_adds_pointcut_advice_and_weaving() -> None:
    builder = ConcernBuilder()
    raw = _candidate()
    assert raw.pointcut is None
    built = builder.enrich(raw)
    assert built.pointcut is not None
    assert built.pointcut.joinpoints
    assert built.advice is not None
    assert built.advice.type == AdviceType.RESPONSE_REQUIREMENT
    assert built.weaving_policy is not None
    assert built.scope is not None
    assert built.lifecycle_state == "active"


def test_enrich_preserves_hand_authored_pointcut() -> None:
    builder = ConcernBuilder()
    custom = Pointcut(
        joinpoints=["before_tool_call"],
        match=PointcutMatch(any_keywords=["rm"]),
    )
    raw = _candidate().model_copy(update={"pointcut": custom})
    built = builder.enrich(raw)
    assert built.pointcut == custom


def test_build_or_update_preserves_store_pointcut_on_reextract() -> None:
    store = MemoryConcernStore()
    builder = ConcernBuilder(store=store)
    first = builder.build_or_update(_candidate())
    assert first.pointcut is not None

    custom_pc = Pointcut(joinpoints=["runtime_start"], match=PointcutMatch(any_keywords=["x"]))
    store.upsert(
        first.model_copy(
            update={
                "pointcut": custom_pc,
                "advice": Advice(type=AdviceType.TOOL_GUARD, content="custom"),
            }
        )
    )

    reextract = _candidate().model_copy(update={"description": "Updated description only."})
    second = builder.build_or_update(reextract)
    assert second.description == "Updated description only."
    assert second.pointcut == custom_pc
    assert second.advice is not None
    assert second.advice.type == AdviceType.TOOL_GUARD


def test_build_many_upserts_to_store() -> None:
    store = MemoryConcernStore()
    builder = ConcernBuilder(store=store)
    second = _candidate().model_copy(update={"id": "c-other", "name": "Other rule"})
    out = builder.build_many([_candidate(), second])
    assert len(out) == 2
    assert store.get("c-test-builder") is not None
    assert store.get("c-other") is not None
