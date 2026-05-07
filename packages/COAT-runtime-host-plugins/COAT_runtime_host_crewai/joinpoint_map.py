"""CrewAI event → joinpoint mapping (placeholder)."""

from __future__ import annotations

CREWAI_EVENT_MAP: dict[str, str] = {
    "crew.kickoff": "runtime_start",
    "agent.execute": "before_reasoning",
    "agent.finish": "after_reasoning",
    "tool.use": "before_tool_call",
    "tool.complete": "after_tool_call",
    "task.complete": "after_response",
}
