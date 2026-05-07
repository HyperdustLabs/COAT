"""LLM client port.

Every concrete provider (openai/anthropic/azure/ollama/stub) implements
this protocol.  The runtime never calls a provider directly.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LLMClient(Protocol):
    """Minimal LLM surface used by extractor / advice / verifier."""

    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        stop: list[str] | None = None,
    ) -> str: ...

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str: ...

    def structured(
        self,
        messages: list[dict[str, Any]],
        *,
        schema: dict[str, Any],
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> dict[str, Any]: ...

    def score(
        self,
        prompt: str,
        candidate: str,
        *,
        criteria: str | None = None,
    ) -> float: ...
