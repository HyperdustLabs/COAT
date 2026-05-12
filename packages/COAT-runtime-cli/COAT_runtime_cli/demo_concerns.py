"""Three "dramatic" demo concerns loaded by ``COATr concern import --demo``.

This module ships **inside** ``COAT-runtime-cli`` (no new package) and is
opt-in: the CLI never seeds the daemon with these by default. They exist
to give a brand-new install something visible to chew on within seconds
of running ``COATr plugin install openclaw``.

Each concern is hand-tuned to fire on a joinpoint that:

* lives in ``COAT_runtime_core.joinpoint.JOINPOINT_CATALOG`` (so the
  built-in catalog accepts the pointcut), **and**
* the OpenClaw adapter actually emits via ``OPENCLAW_EVENT_MAP`` when
  the host subscribes to the corresponding ``agent.*`` event.

Mapping (per :mod:`COAT_runtime_host_openclaw.joinpoint_map`):

==============================  ==============================  ===================
OpenClaw event name             joinpoint                       demo concern
==============================  ==============================  ===================
``agent.started``               ``runtime_start``               ``demo-prompt-prefix``
``agent.before_tool_call``      ``before_tool_call``            ``demo-tool-block``
``agent.memory_write``          ``before_memory_write``         ``demo-memory-tag``
==============================  ==============================  ===================

The OpenClaw scaffold's ``DEFAULT_EVENT_NAMES`` covers
``agent.started`` and ``agent.memory_write`` but **not**
``agent.before_tool_call``; the cookbook section in
``examples/04_openclaw_with_runtime/README.md`` walks through extending
``event_names=`` to wire up the tool-guard demo end-to-end.
"""

from __future__ import annotations

from COAT_runtime_protocol import (
    Advice,
    AdviceType,
    Concern,
    Pointcut,
    WeavingLevel,
    WeavingOperation,
    WeavingPolicy,
)
from COAT_runtime_protocol.envelopes import PointcutMatch

DEMO_PROMPT_PREFIX_ID = "demo-prompt-prefix"
DEMO_TOOL_BLOCK_ID = "demo-tool-block"
DEMO_MEMORY_TAG_ID = "demo-memory-tag"


def _demo_prompt_prefix() -> Concern:
    """RESPONSE_REQUIREMENT — prepend a marker to every response.

    Fires on ``runtime_start`` (mapped from ``agent.started``), so it
    lights up on the very first event the OpenClaw scaffold's default
    subscription emits.
    """
    return Concern(
        id=DEMO_PROMPT_PREFIX_ID,
        name="Demo — runtime banner in system prompt",
        description=(
            "Inserts a small marker so you can confirm at a glance "
            "that COAT-managed concerns reached the system prompt."
        ),
        pointcut=Pointcut(joinpoints=["runtime_start"]),
        advice=Advice(
            type=AdviceType.RESPONSE_REQUIREMENT,
            content="Begin every response with `[COAT demo active]`.",
        ),
        weaving_policy=WeavingPolicy(
            mode=WeavingOperation.INSERT,
            level=WeavingLevel.PROMPT_LEVEL,
            target="runtime_prompt.active_concerns",
            priority=0.5,
        ),
    )


def _demo_tool_block() -> Concern:
    """TOOL_GUARD — refuse ``shell.exec`` calls that mention ``rm -rf``.

    Fires on ``before_tool_call``. The matcher is keyword-based so the
    block fires whether the destructive flag lands in
    ``tool_call.arguments.command`` or any other argument slot; the
    weaving row targets ``tool_call.arguments`` and runs in
    :attr:`WeavingOperation.BLOCK` mode, which the M5 OpenClaw
    ``tool_guard`` interpreter turns into a ``ToolGuardOutcome(blocked
    =True)`` (PR #30).
    """
    return Concern(
        id=DEMO_TOOL_BLOCK_ID,
        name="Demo — block destructive shell commands",
        description=(
            "Refuses any tool call whose arguments mention ``rm -rf``. "
            "Demonstrates the BLOCK weaving mode against "
            "``tool_call.arguments`` (M5 tool_guard interpreter)."
        ),
        pointcut=Pointcut(
            joinpoints=["before_tool_call"],
            match=PointcutMatch(any_keywords=["rm -rf", "rm  -rf"]),
        ),
        advice=Advice(
            type=AdviceType.TOOL_GUARD,
            content="Refusing destructive shell command — `rm -rf` is blocked by demo-tool-block.",
        ),
        weaving_policy=WeavingPolicy(
            mode=WeavingOperation.BLOCK,
            level=WeavingLevel.TOOL_LEVEL,
            target="tool_call.arguments",
            priority=0.9,
        ),
    )


def _demo_memory_tag() -> Concern:
    """MEMORY_WRITE_GUARD — annotate every memory write with a policy hint.

    Fires on ``before_memory_write``. The :class:`OpenClawMemoryBridge`
    (M5 PR #31) mirrors the write into the DCN whenever a
    ``concern_id`` rides along, so this row also shows up in
    ``dcn_store.activation_log()``.
    """
    return Concern(
        id=DEMO_MEMORY_TAG_ID,
        name="Demo — annotate every memory write",
        description=(
            "Adds a lightweight policy note to every memory write. "
            "Pairs with ``OpenClawMemoryBridge`` to mirror the "
            "activation into the DCN."
        ),
        pointcut=Pointcut(joinpoints=["before_memory_write"]),
        advice=Advice(
            type=AdviceType.MEMORY_WRITE_GUARD,
            content="memory.policy=demo-memory-tag: write annotated by demo concern.",
        ),
        weaving_policy=WeavingPolicy(
            mode=WeavingOperation.ANNOTATE,
            level=WeavingLevel.MEMORY_LEVEL,
            target="memory_write.policy_note",
            priority=0.4,
        ),
    )


def demo_concerns() -> list[Concern]:
    """Return the canonical three-concern demo set in stable order."""
    return [_demo_prompt_prefix(), _demo_tool_block(), _demo_memory_tag()]


__all__ = [
    "DEMO_MEMORY_TAG_ID",
    "DEMO_PROMPT_PREFIX_ID",
    "DEMO_TOOL_BLOCK_ID",
    "demo_concerns",
]
