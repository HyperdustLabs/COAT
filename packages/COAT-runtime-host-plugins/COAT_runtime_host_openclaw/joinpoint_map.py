"""OpenClaw event → joinpoint mapping (v0.2 §4.7.1)."""

from __future__ import annotations

OPENCLAW_EVENT_MAP: dict[str, str] = {
    "agent.started": "runtime_start",
    "agent.user_message": "on_user_input",
    "agent.before_llm_call": "before_reasoning",
    "agent.after_llm_call": "after_reasoning",
    "agent.before_tool": "before_tool_call",
    "agent.after_tool": "after_tool_call",
    "agent.before_response": "before_response",
    "agent.after_response": "after_response",
    "agent.memory_write": "before_memory_write",
    "agent.error": "on_error",
}
