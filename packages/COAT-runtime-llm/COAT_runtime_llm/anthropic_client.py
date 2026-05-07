"""Anthropic client — M2 milestone."""

from __future__ import annotations

from typing import Any

from .base import BaseLLMClient


class AnthropicLLMClient(BaseLLMClient):
    def __init__(self, *, model: str = "claude-3-5-sonnet", timeout_seconds: float = 20.0) -> None:
        self._model = model
        self._timeout = timeout_seconds

    def complete(self, prompt: str, **_: Any) -> str:  # pragma: no cover (M2)
        raise NotImplementedError

    def chat(self, messages: list[dict[str, Any]], **_: Any) -> str:  # pragma: no cover (M2)
        raise NotImplementedError

    def structured(
        self,
        messages: list[dict[str, Any]],
        *,
        schema: dict[str, Any],
        **_: Any,
    ) -> dict[str, Any]:  # pragma: no cover (M2)
        raise NotImplementedError

    def score(
        self, prompt: str, candidate: str, *, criteria: str | None = None
    ) -> float:  # pragma: no cover (M2)
        raise NotImplementedError
