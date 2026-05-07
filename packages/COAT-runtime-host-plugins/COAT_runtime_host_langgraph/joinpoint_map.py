"""LangGraph node-name → joinpoint mapping."""

from __future__ import annotations

LANGGRAPH_EVENT_MAP: dict[str, str] = {
    "node.enter": "before_reasoning",
    "node.exit": "after_reasoning",
    "tool.enter": "before_tool_call",
    "tool.exit": "after_tool_call",
    "graph.start": "runtime_start",
    "graph.end": "runtime_stop",
}
