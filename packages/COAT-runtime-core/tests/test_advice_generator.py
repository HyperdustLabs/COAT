"""Tests for :class:`AdviceGenerator` and the bundled templates."""

from __future__ import annotations

from typing import Any

import pytest
from COAT_runtime_core.advice import ADVICE_TEMPLATES, AdviceGenerator
from COAT_runtime_core.advice.templates import AdviceTemplate
from COAT_runtime_protocol import Advice, AdviceType, Concern
from COAT_runtime_protocol.envelopes import WeavingPolicy


def _concern(
    cid: str = "c-1",
    *,
    name: str = "Stay polite",
    description: str = "",
    advice: Advice | None = None,
    target: str | None = None,
) -> Concern:
    policy = WeavingPolicy(target=target) if target else None
    return Concern(
        id=cid,
        name=name,
        description=description,
        advice=advice,
        weaving_policy=policy,
    )


class _StubLLM:
    def __init__(self, reply: str = "stub advice") -> None:
        self.reply = reply
        self.calls: list[tuple[str, dict]] = []

    def complete(self, prompt: str, **kwargs: Any) -> str:
        self.calls.append((prompt, kwargs))
        return self.reply

    def chat(self, *_a: Any, **_k: Any) -> str:
        raise NotImplementedError

    def structured(self, *_a: Any, **_k: Any) -> dict:
        raise NotImplementedError

    def score(self, *_a: Any, **_k: Any) -> float:
        return 0.0


class TestAdviceGenerator:
    def test_pass_through_returns_authored_advice_verbatim(self) -> None:
        gen = AdviceGenerator()
        authored = Advice(type=AdviceType.RESPONSE_REQUIREMENT, content="answer in JSON")
        out = gen.generate(_concern(advice=authored))
        assert out is authored

    def test_template_render_substitutes_concern_fields(self) -> None:
        gen = AdviceGenerator()
        out = gen.generate(_concern(name="Be concise", description="Use ≤ 3 sentences."))
        assert out.type == AdviceType.REASONING_GUIDANCE
        assert "Be concise" in out.content
        assert "Use ≤ 3 sentences." in out.content

    def test_verification_target_routes_to_verification_template(self) -> None:
        gen = AdviceGenerator()
        out = gen.generate(
            _concern(
                name="Cite sources",
                description="Provide URLs.",
                target="runtime_prompt.verification_rules",
            )
        )
        assert out.type == AdviceType.VERIFICATION_RULE
        assert "Cite sources" in out.content

    def test_empty_llm_reply_never_leaks_raw_template_placeholders(self) -> None:
        # Regression for the post-PR-4 review finding: when the LLM
        # returns an empty string we must NOT fall back to the raw
        # ``template.template`` (which still contains literal
        # ``{concern_name}`` etc.). The renderer is invoked again so any
        # surviving placeholders are substituted; if even that comes out
        # empty, the concern's name is the safety net.
        original = ADVICE_TEMPLATES[AdviceType.REASONING_GUIDANCE]
        ADVICE_TEMPLATES[AdviceType.REASONING_GUIDANCE] = AdviceTemplate(
            type=AdviceType.REASONING_GUIDANCE,
            template="",  # forces the LLM branch
        )
        try:
            stub = _StubLLM(reply="   ")  # whitespace -> empty after strip
            gen = AdviceGenerator(llm=stub)
            out = gen.generate(_concern(name="My concern"))
            assert "{" not in out.content and "}" not in out.content
            assert out.content == "My concern"
        finally:
            ADVICE_TEMPLATES[AdviceType.REASONING_GUIDANCE] = original

    def test_falls_back_to_llm_when_no_template_registered(self) -> None:
        # Drop the template for the inferred type to force the LLM path.
        original = ADVICE_TEMPLATES.pop(AdviceType.REASONING_GUIDANCE)
        try:
            stub = _StubLLM(reply="LLM advice")
            gen = AdviceGenerator(llm=stub)
            out = gen.generate(_concern(name="x"))
            assert out.content == "LLM advice"
            assert len(stub.calls) == 1
        finally:
            ADVICE_TEMPLATES[AdviceType.REASONING_GUIDANCE] = original

    def test_raises_when_no_template_and_no_llm(self) -> None:
        original = ADVICE_TEMPLATES.pop(AdviceType.REASONING_GUIDANCE)
        try:
            gen = AdviceGenerator()
            with pytest.raises(RuntimeError, match="No advice template"):
                gen.generate(_concern())
        finally:
            ADVICE_TEMPLATES[AdviceType.REASONING_GUIDANCE] = original

    def test_every_advice_type_has_a_template(self) -> None:
        # Regression: hosts may iterate over the catalog assuming
        # full coverage. If a new AdviceType is added without a
        # template the test fails loud.
        assert set(ADVICE_TEMPLATES.keys()) == set(AdviceType)


class TestAdviceTemplate:
    def test_render_handles_missing_keys_silently(self) -> None:
        tpl = AdviceTemplate(
            type=AdviceType.REASONING_GUIDANCE,
            template="A {present} B {absent}",
        )
        rendered = tpl.render(present="ok")
        assert rendered == "A ok B "
