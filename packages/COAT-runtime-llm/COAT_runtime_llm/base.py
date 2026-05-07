"""Common base for LLM clients."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseLLMClient(ABC):
    """Convenience base — concrete providers may inherit from this."""

    @abstractmethod
    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        stop: list[str] | None = None,
    ) -> str: ...

    @abstractmethod
    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str: ...

    @abstractmethod
    def structured(
        self,
        messages: list[dict[str, Any]],
        *,
        schema: dict[str, Any],
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> dict[str, Any]: ...

    @abstractmethod
    def score(
        self,
        prompt: str,
        candidate: str,
        *,
        criteria: str | None = None,
    ) -> float: ...
