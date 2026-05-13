"""Hermes event → joinpoint mapping (placeholder, refined at M7)."""

from __future__ import annotations

HERMES_EVENT_MAP: dict[str, str] = {
    "session.start": "runtime_start",
    "user.message": "on_user_input",
    "llm.request": "before_reasoning",
    "llm.response": "after_reasoning",
    "tool.invoke": "before_tool_call",
    "tool.result": "after_tool_call",
    "agent.respond": "before_response",
    "session.error": "on_error",
}
