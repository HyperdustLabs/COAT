"""Default advice templates, one per advice type.

Each template is a short prompt fragment that the host LLM can read
verbatim. They use a deliberately minimal placeholder vocabulary so
:class:`AdviceGenerator` can substitute values from a Concern + context
without bringing in a templating engine:

    {concern_name}   — concern.name
    {concern_id}     — concern.id
    {description}    — concern.description (may be empty)
    {rationale}      — concern.advice.rationale or empty string

Hosts that need richer rendering (Jinja, Mustache, …) should subclass
:class:`AdviceGenerator` and override :meth:`render`.
"""

from __future__ import annotations

from dataclasses import dataclass

from opencoat_runtime_protocol import AdviceType


@dataclass(frozen=True)
class AdviceTemplate:
    type: AdviceType
    template: str
    description: str = ""

    def render(self, **fields: str) -> str:
        """Substitute ``{name}`` placeholders without raising on unknown keys."""
        return self.template.format_map(_SafeDict(fields))


class _SafeDict(dict):
    """``str.format_map`` helper: missing keys render as empty strings."""

    def __missing__(self, key: str) -> str:
        return ""


ADVICE_TEMPLATES: dict[AdviceType, AdviceTemplate] = {
    AdviceType.REASONING_GUIDANCE: AdviceTemplate(
        type=AdviceType.REASONING_GUIDANCE,
        template="When reasoning, keep in mind: {concern_name}. {description}",
        description="Steers the chain of thought without changing the goal.",
    ),
    AdviceType.PLANNING_GUIDANCE: AdviceTemplate(
        type=AdviceType.PLANNING_GUIDANCE,
        template="While planning the next steps, ensure: {concern_name}. {description}",
        description="Adds a constraint or preference to the planner.",
    ),
    AdviceType.DECISION_GUIDANCE: AdviceTemplate(
        type=AdviceType.DECISION_GUIDANCE,
        template="Before committing to a decision, weigh: {concern_name}. {description}",
        description="Surfaces a factor the chooser must consider.",
    ),
    AdviceType.TOOL_GUARD: AdviceTemplate(
        type=AdviceType.TOOL_GUARD,
        template="Tool-call guard ({concern_name}): {description}",
        description="Hard constraint applied at the tool boundary.",
    ),
    AdviceType.RESPONSE_REQUIREMENT: AdviceTemplate(
        type=AdviceType.RESPONSE_REQUIREMENT,
        template="Response must satisfy: {concern_name}. {description}",
        description="Output-shape requirement (format, length, fields).",
    ),
    AdviceType.VERIFICATION_RULE: AdviceTemplate(
        type=AdviceType.VERIFICATION_RULE,
        template="Verify after responding: {concern_name}. {description}",
        description="Post-hoc check evaluated by the verifier.",
    ),
    AdviceType.MEMORY_WRITE_GUARD: AdviceTemplate(
        type=AdviceType.MEMORY_WRITE_GUARD,
        template="Memory write guard ({concern_name}): {description}",
        description="Restricts what may be persisted.",
    ),
    AdviceType.REFLECTION_PROMPT: AdviceTemplate(
        type=AdviceType.REFLECTION_PROMPT,
        template="Reflect briefly: {concern_name}. {description}",
        description="Triggers a reflection turn.",
    ),
    AdviceType.REWRITE_GUIDANCE: AdviceTemplate(
        type=AdviceType.REWRITE_GUIDANCE,
        template="When rewriting, apply: {concern_name}. {description}",
        description="Steers a rewrite/refinement pass.",
    ),
    AdviceType.SUPPRESS_INSTRUCTION: AdviceTemplate(
        type=AdviceType.SUPPRESS_INSTRUCTION,
        template="Suppress: {concern_name}. {description}",
        description="Silences an otherwise-active behaviour.",
    ),
    AdviceType.ESCALATION_NOTICE: AdviceTemplate(
        type=AdviceType.ESCALATION_NOTICE,
        template="Escalation: {concern_name}. {description} {rationale}",
        description="Surfaces a host-visible alert for human/system follow-up.",
    ),
}


__all__ = ["ADVICE_TEMPLATES", "AdviceTemplate"]
