"""AutoGen event → joinpoint mapping (placeholder)."""

from __future__ import annotations

AUTOGEN_EVENT_MAP: dict[str, str] = {
    "ConversableAgent.on_receive": "on_user_input",
    "ConversableAgent.before_reply": "before_reasoning",
    "ConversableAgent.after_reply": "after_reasoning",
    "tool.before": "before_tool_call",
    "tool.after": "after_tool_call",
}
