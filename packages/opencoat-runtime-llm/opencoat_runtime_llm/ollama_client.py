"""Ollama client — M2 milestone."""

from __future__ import annotations

from typing import Any

from .base import BaseLLMClient


class OllamaLLMClient(BaseLLMClient):
    def __init__(
        self,
        *,
        model: str,
        base_url: str = "http://127.0.0.1:11434",
        timeout_seconds: float = 30.0,
    ) -> None:
        self._model = model
        self._base_url = base_url
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
