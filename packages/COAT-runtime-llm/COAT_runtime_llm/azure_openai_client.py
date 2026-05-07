"""Azure OpenAI client — M2 milestone."""

from __future__ import annotations

from typing import Any

from .base import BaseLLMClient


class AzureOpenAILLMClient(BaseLLMClient):
    def __init__(
        self,
        *,
        deployment: str,
        endpoint: str,
        api_version: str = "2024-06-01",
        timeout_seconds: float = 20.0,
    ) -> None:
        self._deployment = deployment
        self._endpoint = endpoint
        self._api_version = api_version
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
