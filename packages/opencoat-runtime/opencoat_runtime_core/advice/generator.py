"""Default :class:`AdvicePlugin` — turn a Concern + context into an Advice.

Resolution order (M1):

1. **Pass-through** — if the concern already carries ``concern.advice``,
   return it verbatim. Hosts that hand-author concerns get exactly what
   they asked for.
2. **Template** — render the matching :class:`AdviceTemplate` from
   :data:`ADVICE_TEMPLATES`, substituting the concern's name / id /
   description / rationale.
3. **LLM fallback** — only if both the concern carries no advice *and*
   no template is registered for its inferred type. M1 never reaches
   this branch with the default catalog (every type has a template) but
   the seam exists for future advice types.

The default *inferred type* is :class:`AdviceType.REASONING_GUIDANCE` —
the lowest-impact category — chosen so a partially-specified concern
never silently escalates the kind of intervention.
"""

from __future__ import annotations

from opencoat_runtime_protocol import Advice, AdviceType, Concern

from ..ports import LLMClient
from ..ports.advice_plugin import AdvicePlugin
from ..types import JSON
from .templates import ADVICE_TEMPLATES, AdviceTemplate


class AdviceGenerator(AdvicePlugin):
    """Generate advice using templates first, falling back to LLM when needed."""

    _DEFAULT_TYPE = AdviceType.REASONING_GUIDANCE

    def __init__(self, *, llm: LLMClient | None = None) -> None:
        self._llm = llm

    def generate(self, concern: Concern, context: JSON | None = None) -> Advice:
        if concern.advice is not None:
            return concern.advice

        advice_type = self._infer_type(concern)
        template = ADVICE_TEMPLATES.get(advice_type)
        if template is not None:
            content = template.render(
                concern_name=concern.name,
                concern_id=concern.id,
                description=concern.description or "",
                rationale="",
            ).strip()
            if content:
                return Advice(type=advice_type, content=content)

        if self._llm is None:
            raise RuntimeError(
                f"No advice template for type={advice_type!r} and no LLM "
                f"fallback configured (concern={concern.id!r})."
            )

        prompt = self._llm_prompt(concern, advice_type, context)
        generated = self._llm.complete(prompt, max_tokens=200).strip()
        if not generated:
            # NEVER leak the raw, unsubstituted template (literal
            # ``{concern_name}``…). If the template renders to non-empty
            # text use that, otherwise fall back to the concern's name —
            # always something a human reader can parse.
            generated = self._safe_fallback(concern, template)
        return Advice(type=advice_type, content=generated)

    @staticmethod
    def _safe_fallback(concern: Concern, template: AdviceTemplate | None) -> str:
        if template is not None:
            rendered = template.render(
                concern_name=concern.name,
                concern_id=concern.id,
                description=concern.description or "",
                rationale="",
            ).strip()
            if rendered:
                return rendered
        return concern.name

    @staticmethod
    def _infer_type(concern: Concern) -> AdviceType:
        # Concerns whose policy points at a verification target should
        # produce verification rules; others fall back to reasoning.
        policy = concern.weaving_policy
        if policy is not None and policy.target and "verification" in policy.target:
            return AdviceType.VERIFICATION_RULE
        return AdviceGenerator._DEFAULT_TYPE

    @staticmethod
    def _llm_prompt(
        concern: Concern,
        advice_type: AdviceType,
        context: JSON | None,
    ) -> str:
        ctx_summary = ""
        if context:
            ctx_summary = "\nContext keys: " + ", ".join(sorted(context.keys()))
        return (
            f"Generate a single concise {advice_type.value} for the concern "
            f"'{concern.name}'. Description: {concern.description or '(none)'}."
            f"{ctx_summary}\nReturn only the advice text."
        )


__all__ = ["AdviceGenerator"]
