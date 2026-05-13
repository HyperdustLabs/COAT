"""Catalog of well-known weaving targets (v0.1 §15.2 + the standard prompt paths).

A *target* identifies *where* an advice will be inserted (e.g.
``runtime_prompt.verification_rules``, ``tool_call.arguments.amount``).
The host adapter is responsible for honouring these targets.
"""

from __future__ import annotations

from opencoat_runtime_protocol import WeavingLevel

WEAVING_TARGETS: dict[WeavingLevel, tuple[str, ...]] = {
    WeavingLevel.PROMPT_LEVEL: (
        "runtime_prompt.active_concerns",
        "runtime_prompt.tool_instructions",
        "runtime_prompt.output_format",
        "runtime_prompt.verification_rules",
        "runtime_prompt.reasoning_guidance",
    ),
    WeavingLevel.SPAN_LEVEL: ("user_message.span:*",),
    WeavingLevel.TOKEN_LEVEL: ("user_message.token:*",),
    WeavingLevel.TOOL_LEVEL: ("tool_call.arguments.*",),
    WeavingLevel.MEMORY_LEVEL: ("memory_write.*",),
    WeavingLevel.OUTPUT_LEVEL: ("response.json.*", "response.text"),
    WeavingLevel.VERIFICATION_LEVEL: ("runtime_prompt.verification_rules",),
    WeavingLevel.REFLECTION_LEVEL: ("runtime_prompt.reflection_prompt",),
}

__all__ = ["WEAVING_TARGETS", "WeavingLevel"]
