"""Concern Extractor — v0.1 §20.1.

Identifies candidate Concerns from any of:

* user input
* dialogue context
* tool results
* environment events
* draft outputs
* feedback
* memory
* host explicit plans
"""

from __future__ import annotations

from dataclasses import dataclass, field

from COAT_runtime_protocol import COPR, Concern

from ..ports import LLMClient


@dataclass(frozen=True)
class ExtractionResult:
    """Outcome of one extraction call."""

    candidates: tuple[Concern, ...] = ()
    rejected: tuple[str, ...] = field(default_factory=tuple)


class ConcernExtractor:
    """Turn arbitrary inputs into candidate Concerns.

    The extractor is LLM-driven by default but degrades gracefully via the
    ``stub`` LLM provider for offline tests.
    """

    def __init__(self, *, llm: LLMClient) -> None:
        self._llm = llm

    def extract_from_user_input(self, text: str, *, copr: COPR | None = None) -> ExtractionResult:
        raise NotImplementedError

    def extract_from_tool_result(self, tool_name: str, result: dict) -> ExtractionResult:
        raise NotImplementedError

    def extract_from_draft_output(self, draft: str) -> ExtractionResult:
        raise NotImplementedError

    def extract_from_feedback(self, feedback: dict) -> ExtractionResult:
        raise NotImplementedError
