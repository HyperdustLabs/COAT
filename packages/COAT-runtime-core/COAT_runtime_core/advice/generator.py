"""Default :class:`AdvicePlugin` — turn a Concern + context into an Advice."""

from __future__ import annotations

from COAT_runtime_protocol import Advice, Concern

from ..ports import LLMClient
from ..ports.advice_plugin import AdvicePlugin
from ..types import JSON


class AdviceGenerator(AdvicePlugin):
    """Generate advice using templates first, falling back to LLM when needed."""

    def __init__(self, *, llm: LLMClient) -> None:
        self._llm = llm

    def generate(self, concern: Concern, context: JSON | None = None) -> Advice:
        raise NotImplementedError
