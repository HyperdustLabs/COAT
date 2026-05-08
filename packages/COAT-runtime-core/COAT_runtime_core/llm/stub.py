"""Deterministic in-process :class:`LLMClient` for tests, examples, and the
M1 in-proc happy path.

Design goals
------------
* **No network, no I/O** — safe to run in CI sandboxes and offline
  developer environments.
* **Deterministic** — given the same prompt the stub returns the same
  reply forever, so snapshot tests stay stable.
* **Scriptable** — callers can pre-load canned replies (``replies={...}``)
  or a generic default for prompts they didn't anticipate. The stub
  keeps the call log so tests can assert on the prompts it received.

The stub deliberately keeps its surface tiny: the four ``LLMClient``
methods plus a couple of test-only helpers. It is *not* meant to model
real LLM quirks — for that, use the real adapter under a recorder.
"""

from __future__ import annotations

from typing import Any


class StubLLMClient:
    """A deterministic, scriptable stand-in for :class:`LLMClient`.

    Parameters
    ----------
    default_completion:
        Returned by :meth:`complete` when no scripted reply matches.
    default_chat:
        Returned by :meth:`chat` when no scripted reply matches.
    default_structured:
        Returned by :meth:`structured` when no scripted reply matches.
    default_score:
        Returned by :meth:`score` when no scripted score matches.
    replies:
        Optional mapping of *prompt prefix* → reply for :meth:`complete`.
        The first prefix that matches the prompt wins; insertion order
        decides ties.
    """

    def __init__(
        self,
        *,
        default_completion: str = "stub-completion",
        default_chat: str = "stub-chat",
        default_structured: dict[str, Any] | None = None,
        default_score: float = 0.5,
        replies: dict[str, str] | None = None,
    ) -> None:
        self._default_completion = default_completion
        self._default_chat = default_chat
        self._default_structured = (
            dict(default_structured) if default_structured is not None else {}
        )
        self._default_score = default_score
        self._replies: dict[str, str] = dict(replies or {})
        self._calls: list[tuple[str, str, dict[str, Any]]] = []

    # --- LLMClient surface -------------------------------------------------

    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        stop: list[str] | None = None,
    ) -> str:
        self._calls.append(
            (
                "complete",
                prompt,
                {"max_tokens": max_tokens, "temperature": temperature, "stop": stop},
            )
        )
        for prefix, reply in self._replies.items():
            if prompt.startswith(prefix):
                return reply
        return self._default_completion

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        self._calls.append(
            ("chat", repr(messages), {"max_tokens": max_tokens, "temperature": temperature})
        )
        return self._default_chat

    def structured(
        self,
        messages: list[dict[str, Any]],
        *,
        schema: dict[str, Any],
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        self._calls.append(
            (
                "structured",
                repr(messages),
                {"schema_keys": sorted(schema.keys()), "max_tokens": max_tokens},
            )
        )
        return dict(self._default_structured)

    def score(
        self,
        prompt: str,
        candidate: str,
        *,
        criteria: str | None = None,
    ) -> float:
        self._calls.append(("score", prompt, {"candidate": candidate, "criteria": criteria}))
        return self._default_score

    # --- test-only helpers -------------------------------------------------

    @property
    def calls(self) -> list[tuple[str, str, dict[str, Any]]]:
        """Log of (method, prompt-or-messages, kwargs) tuples in call order."""
        return list(self._calls)

    def reset(self) -> None:
        """Forget every recorded call (handy between sub-tests)."""
        self._calls.clear()


__all__ = ["StubLLMClient"]
