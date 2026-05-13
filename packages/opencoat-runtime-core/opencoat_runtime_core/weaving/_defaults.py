"""Per-advice-type defaults used by :class:`ConcernWeaver` when the concern's
``weaving_policy`` does not pin a particular ``mode`` / ``level`` / ``target``.

These mappings encode the v0.1 §15.2 conventions: an *advice type* implies
a *weaving operation* and a *weaving level*, which together resolve a
default *target path* the host adapter can route on.

Hosts (or per-concern policies) can override any of these — the weaver
treats the policy as authoritative whenever a field is set.
"""

from __future__ import annotations

from typing import Final

from opencoat_runtime_protocol import AdviceType, WeavingLevel, WeavingOperation

DEFAULT_MODE: Final[dict[AdviceType, WeavingOperation]] = {
    AdviceType.REASONING_GUIDANCE: WeavingOperation.INSERT,
    AdviceType.PLANNING_GUIDANCE: WeavingOperation.INSERT,
    AdviceType.DECISION_GUIDANCE: WeavingOperation.ANNOTATE,
    AdviceType.TOOL_GUARD: WeavingOperation.BLOCK,
    AdviceType.RESPONSE_REQUIREMENT: WeavingOperation.INSERT,
    AdviceType.VERIFICATION_RULE: WeavingOperation.VERIFY,
    AdviceType.MEMORY_WRITE_GUARD: WeavingOperation.BLOCK,
    AdviceType.REFLECTION_PROMPT: WeavingOperation.INSERT,
    AdviceType.REWRITE_GUIDANCE: WeavingOperation.REWRITE,
    AdviceType.SUPPRESS_INSTRUCTION: WeavingOperation.SUPPRESS,
    AdviceType.ESCALATION_NOTICE: WeavingOperation.ESCALATE,
}

DEFAULT_LEVEL: Final[dict[AdviceType, WeavingLevel]] = {
    AdviceType.REASONING_GUIDANCE: WeavingLevel.PROMPT_LEVEL,
    AdviceType.PLANNING_GUIDANCE: WeavingLevel.PROMPT_LEVEL,
    AdviceType.DECISION_GUIDANCE: WeavingLevel.PROMPT_LEVEL,
    AdviceType.TOOL_GUARD: WeavingLevel.TOOL_LEVEL,
    AdviceType.RESPONSE_REQUIREMENT: WeavingLevel.OUTPUT_LEVEL,
    AdviceType.VERIFICATION_RULE: WeavingLevel.VERIFICATION_LEVEL,
    AdviceType.MEMORY_WRITE_GUARD: WeavingLevel.MEMORY_LEVEL,
    AdviceType.REFLECTION_PROMPT: WeavingLevel.REFLECTION_LEVEL,
    AdviceType.REWRITE_GUIDANCE: WeavingLevel.OUTPUT_LEVEL,
    AdviceType.SUPPRESS_INSTRUCTION: WeavingLevel.PROMPT_LEVEL,
    AdviceType.ESCALATION_NOTICE: WeavingLevel.PROMPT_LEVEL,
}

DEFAULT_TARGET: Final[dict[AdviceType, str]] = {
    AdviceType.REASONING_GUIDANCE: "runtime_prompt.reasoning_guidance",
    AdviceType.PLANNING_GUIDANCE: "runtime_prompt.active_concerns",
    AdviceType.DECISION_GUIDANCE: "runtime_prompt.active_concerns",
    AdviceType.TOOL_GUARD: "tool_call.arguments.*",
    AdviceType.RESPONSE_REQUIREMENT: "runtime_prompt.output_format",
    AdviceType.VERIFICATION_RULE: "runtime_prompt.verification_rules",
    AdviceType.MEMORY_WRITE_GUARD: "memory_write.*",
    AdviceType.REFLECTION_PROMPT: "runtime_prompt.reflection_prompt",
    AdviceType.REWRITE_GUIDANCE: "response.text",
    AdviceType.SUPPRESS_INSTRUCTION: "runtime_prompt.active_concerns",
    AdviceType.ESCALATION_NOTICE: "runtime_prompt.active_concerns",
}


__all__ = ["DEFAULT_LEVEL", "DEFAULT_MODE", "DEFAULT_TARGET"]
