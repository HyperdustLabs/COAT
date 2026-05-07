"""Numeric joinpoint level enum (v0.1 §12.2)."""

from __future__ import annotations

from enum import IntEnum


class JoinpointLevel(IntEnum):
    RUNTIME = 0
    LIFECYCLE = 1
    MESSAGE = 2
    PROMPT_SECTION = 3
    SEMANTIC_SPAN = 4
    TOKEN = 5
    STRUCTURE_FIELD = 6
    THOUGHT_UNIT = 7

    @property
    def label(self) -> str:
        return _LABELS[self]


_LABELS: dict[JoinpointLevel, str] = {
    JoinpointLevel.RUNTIME: "runtime",
    JoinpointLevel.LIFECYCLE: "lifecycle",
    JoinpointLevel.MESSAGE: "message",
    JoinpointLevel.PROMPT_SECTION: "prompt_section",
    JoinpointLevel.SEMANTIC_SPAN: "span",
    JoinpointLevel.TOKEN: "token",
    JoinpointLevel.STRUCTURE_FIELD: "structure_field",
    JoinpointLevel.THOUGHT_UNIT: "thought_unit",
}
