"""OpenClaw event → joinpoint mapping (v0.2 §4.7.1).

Single source of truth for what each well-known OpenClaw event turns
into on the OpenCOAT side. We surface the table both as:

* ``OPENCLAW_EVENT_MAP: dict[str, str]`` — the public, host-agnostic
  shape every existing test / introspection tool can read. Plain
  strings on both sides so the table survives even if the
  :class:`~.events.OpenClawEventName` enum is later extended.
* ``lookup_joinpoint(event_name)`` — defensive accessor returning
  ``None`` for unknown events. The adapter uses this to honour the
  ``HostAdapter`` protocol's "return ``None`` for events I don't know
  about" contract instead of raising.

The mapping is intentionally small — adapters bolt extra payload
shaping on top (span extraction, tool guard, memory bridge) rather
than smuggling host-specific names into this table.
"""

from __future__ import annotations

from .events import OpenClawEventName

# Mapping is authored against the enum so the type system catches
# typos in event names; we export the str-keyed dict view below so
# nothing outside this module has to import the enum.
_OPENCLAW_EVENT_MAP: dict[OpenClawEventName, str] = {
    OpenClawEventName.AGENT_STARTED: "runtime_start",
    OpenClawEventName.AGENT_USER_MESSAGE: "on_user_input",
    OpenClawEventName.AGENT_BEFORE_LLM_CALL: "before_reasoning",
    OpenClawEventName.AGENT_AFTER_LLM_CALL: "after_reasoning",
    OpenClawEventName.AGENT_BEFORE_TOOL: "before_tool_call",
    OpenClawEventName.AGENT_AFTER_TOOL: "after_tool_call",
    OpenClawEventName.AGENT_BEFORE_RESPONSE: "before_response",
    OpenClawEventName.AGENT_AFTER_RESPONSE: "after_response",
    OpenClawEventName.AGENT_MEMORY_WRITE: "before_memory_write",
    OpenClawEventName.AGENT_ERROR: "on_error",
}

OPENCLAW_EVENT_MAP: dict[str, str] = {k.value: v for k, v in _OPENCLAW_EVENT_MAP.items()}
"""Stringified copy of the well-known OpenClaw → joinpoint mapping."""


def lookup_joinpoint(event_name: str) -> str | None:
    """Return the joinpoint name for ``event_name`` or ``None`` if unknown."""
    return OPENCLAW_EVENT_MAP.get(event_name)


__all__ = ["OPENCLAW_EVENT_MAP", "lookup_joinpoint"]
