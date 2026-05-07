"""Deterministic, dependency-free LLM client used for tests / MVP runs.

M0 only declares the class. M1 will fill in trivial deterministic answers so
the in-proc happy path can run end-to-end without network access.
"""

from __future__ import annotations

from typing import Any

from .base import BaseLLMClient


class StubLLMClient(BaseLLMClient):
    """Returns canned responses keyed by prompt prefix.

    Construct with ``responses=[("prefix", "reply")]`` to add deterministic
    matches. Anything unmatched returns the configured ``default`` reply.
    """

    def __init__(
        self,
        *,
        responses: list[tuple[str, str]] | None = None,
        default: str = "",
    ) -> None:
        self._responses = list(responses or [])
        self._default = default

    # The actual implementations land in M1 — they need to honour the
    # AdvicePlugin / VerificationRule contracts the runtime expects.

    def complete(self, prompt: str, **_: Any) -> str:
        raise NotImplementedError

    def chat(self, messages: list[dict[str, Any]], **_: Any) -> str:
        raise NotImplementedError

    def structured(
        self,
        messages: list[dict[str, Any]],
        *,
        schema: dict[str, Any],
        **_: Any,
    ) -> dict[str, Any]:
        raise NotImplementedError

    def score(self, prompt: str, candidate: str, *, criteria: str | None = None) -> float:
        raise NotImplementedError
