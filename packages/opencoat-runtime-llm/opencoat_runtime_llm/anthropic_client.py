"""Anthropic :class:`LLMClient` adapter.

Second real provider on the M2 track (PR-2). Mirrors the design of
:mod:`opencoat_runtime_llm.openai_client` so swapping providers is a
constructor change in the host, not a refactor in the runtime.

Differences from the OpenAI adapter that matter
-----------------------------------------------
* **System prompt is a separate field.** Anthropic's
  ``messages.create`` takes ``system=`` as a top-level kwarg rather
  than a ``role: "system"`` entry inside ``messages``. The chat
  surface accepts the OpenAI-style mixed list and splits the system
  rows out before sending — concatenating multiple system entries
  with blank lines so policy + instructions can be layered.
* **``max_tokens`` is required by the API.** The OpenAI adapter can
  omit it; Anthropic 4xxs the request without it. We always have a
  default (1024) and never pass ``None`` down. The ``score()`` knob
  stays non-optional for the same reason.
* **No native JSON-schema mode.** Anthropic doesn't ship a
  ``response_format=json_schema`` equivalent. Instead we use **forced
  tool use** — define a single tool whose ``input_schema`` is the
  caller's schema, and pass ``tool_choice={"type": "tool", ...}`` so
  the model is required to fill the tool inputs. The schema is
  validated server-side, and the structured output comes back as the
  ``tool_use`` block's ``input`` dict. This is the same
  reliability tier as OpenAI's strict mode for production schemas.
* **``stop_sequences`` instead of ``stop``.** Renamed at the kwarg
  layer; the abstract ``LLMClient`` surface still talks about
  ``stop``.
* **Response shape.** ``response.content`` is a list of
  ``ContentBlock``s (text / tool_use / image / …). ``_extract_text``
  walks them defensively so partial / multi-block responses degrade
  to "" rather than raise — same fail-soft policy as the OpenAI
  adapter so :meth:`score` can fall back to 0.5 instead of crashing
  the turn.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from .base import BaseLLMClient

_LOG = logging.getLogger(__name__)

# Same regex as the OpenAI adapter — lifted intentionally rather than
# imported so the two clients stay decoupled. See the OpenAI module
# for the rationale on the scientific-notation tail.
_FLOAT_RE = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?")


class AnthropicLLMClient(BaseLLMClient):
    """Concrete :class:`LLMClient` backed by the Anthropic Python SDK.

    Parameters
    ----------
    model:
        Default model name. ``claude-3-5-sonnet-latest`` is a
        balanced default; pick a Haiku variant for cheap / fast and
        an Opus variant for hardest reasoning.
    api_key:
        Explicit API key. ``None`` falls back to ``ANTHROPIC_API_KEY``
        in the environment, mirroring the SDK's own behaviour.
        Constructing without either raises
        :class:`AnthropicClientError` so misconfiguration fails fast
        at runtime startup, not on the first turn.
    base_url:
        Override the API endpoint. Useful for on-prem proxies and
        Anthropic-compatible gateways. ``None`` uses the SDK default.
    timeout_seconds:
        Per-request timeout in seconds.
    default_temperature:
        Used when a method receives ``temperature=None``. ``None``
        lets the SDK / model pick. The default ``0.0`` keeps the
        verifier and structured paths deterministic.
    default_max_tokens:
        Anthropic requires ``max_tokens`` on every request. We cap at
        1024 by default — large enough for chat replies, small
        enough that the score path stays cheap. Hosts producing long
        documents should bump this explicitly.
    score_max_tokens:
        Token cap applied specifically to :meth:`score`. Stays an
        ``int`` (never ``None``) because Anthropic mandates
        ``max_tokens``. The default of ``8`` is plenty for the
        single-number reply the score heuristic expects.
    """

    DEFAULT_MODEL = "claude-3-5-sonnet-latest"
    DEFAULT_MAX_TOKENS = 1024
    DEFAULT_SCORE_MAX_TOKENS = 8

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float = 20.0,
        default_temperature: float | None = 0.0,
        default_max_tokens: int = DEFAULT_MAX_TOKENS,
        score_max_tokens: int = DEFAULT_SCORE_MAX_TOKENS,
    ) -> None:
        try:
            from anthropic import Anthropic
        except ImportError as exc:
            raise AnthropicClientError(
                "AnthropicLLMClient requires the optional 'anthropic' extra. "
                "Install it with `pip install opencoat-runtime-llm[anthropic]`."
            ) from exc

        resolved_key = api_key if api_key is not None else os.environ.get("ANTHROPIC_API_KEY")
        if not resolved_key:
            raise AnthropicClientError(
                "ANTHROPIC_API_KEY is not set and no api_key was passed. "
                "Pass api_key=... explicitly or set the ANTHROPIC_API_KEY "
                "environment variable."
            )

        # Negative ``max_tokens`` is unambiguously invalid; we keep
        # the construction-time check so the failure mode is clear at
        # startup rather than on the first turn. ``0`` is permitted so
        # we don't pre-empt provider-side modes that opt into a
        # zero-completion request (Codex P2 on PR-8) — if Anthropic
        # rejects the value the SDK still surfaces a clean error.
        if default_max_tokens < 0:
            raise AnthropicClientError(
                f"default_max_tokens must be >= 0; got {default_max_tokens!r}"
            )
        if score_max_tokens < 0:
            raise AnthropicClientError(f"score_max_tokens must be >= 0; got {score_max_tokens!r}")

        self._model = model
        self._timeout = timeout_seconds
        self._default_temperature = default_temperature
        self._default_max_tokens = default_max_tokens
        self._score_max_tokens = score_max_tokens
        self._client = Anthropic(
            api_key=resolved_key,
            base_url=base_url,
            timeout=timeout_seconds,
        )

    # ------------------------------------------------------------------
    # LLMClient surface
    # ------------------------------------------------------------------

    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        stop: list[str] | None = None,
    ) -> str:
        return self.chat(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
            stop=stop,
        )

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        stop: list[str] | None = None,
    ) -> str:
        # OpenAI-style mixed messages list → (system, non-system).
        # ``system`` is ``None`` when no system row was supplied,
        # ``str`` for the all-string case, or ``list[block]`` when
        # the caller used Anthropic block-form content (cache_control
        # markers etc).
        system, conversation = _split_system(messages)
        kwargs = self._call_kwargs(
            max_tokens=max_tokens,
            temperature=temperature,
            stop=stop,
        )
        if system is not None:
            kwargs["system"] = system
        response = self._client.messages.create(
            model=self._model,
            messages=conversation,
            **kwargs,
        )
        return _extract_text(response)

    def structured(
        self,
        messages: list[dict[str, Any]],
        *,
        schema: dict[str, Any],
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        # Forced tool use is Anthropic's recommended path for strict
        # schema-conformant output. We define exactly one tool whose
        # ``input_schema`` is the caller's schema and pin the model
        # to it via ``tool_choice``. The model fills the tool's input
        # dict, which we hand back to the caller as the structured
        # response. The text channel is unused on the way back; some
        # gateways still emit a leading text block, so we walk every
        # block in the response and pick the first ``tool_use`` one.
        tool_name = "respond"
        tools = [
            {
                "name": tool_name,
                "description": "Return the structured response payload.",
                "input_schema": schema,
            }
        ]
        system, conversation = _split_system(messages)
        kwargs = self._call_kwargs(max_tokens=max_tokens, temperature=temperature)
        if system is not None:
            kwargs["system"] = system
        response = self._client.messages.create(
            model=self._model,
            messages=conversation,
            tools=tools,
            tool_choice={"type": "tool", "name": tool_name},
            **kwargs,
        )

        payload = _extract_tool_input(response, tool_name)
        if payload is None:
            raise AnthropicClientError(
                "structured() got no tool_use block from Anthropic — "
                "the model declined to call the forced tool"
            )
        return payload

    def score(
        self,
        prompt: str,
        candidate: str,
        *,
        criteria: str | None = None,
    ) -> float:
        instruction = (
            "Rate how well the candidate satisfies the prompt. "
            "Reply with a single number between 0.0 and 1.0 (0.0 = not at all, "
            "1.0 = perfectly). Reply with ONLY the number, no explanation."
        )
        if criteria:
            instruction += f"\nCriteria: {criteria.strip()}"

        # ``score`` deliberately bypasses :meth:`chat` / :meth:`_call_kwargs`
        # so the per-call kwargs are exactly what we want — same Codex P1
        # rationale as the OpenAI adapter (PR-7). Going through ``chat``
        # would silently fall back to ``default_max_tokens``, which is
        # wasteful (1024 tokens for a one-token reply) and makes
        # ``score()`` non-deterministic when the host wires a non-zero
        # ``default_temperature``.
        kwargs: dict[str, Any] = {
            # Force determinism: scoring shouldn't drift between
            # otherwise-identical calls.
            "temperature": 0.0,
            "max_tokens": self._score_max_tokens,
        }
        response = self._client.messages.create(
            model=self._model,
            messages=[
                {"role": "user", "content": f"Prompt:\n{prompt}\n\nCandidate:\n{candidate}"},
            ],
            system=instruction,
            **kwargs,
        )
        text = _extract_text(response)

        match = _FLOAT_RE.search(text)
        if match is None:
            _LOG.warning("score() got unparseable reply %r; falling back to 0.5", text)
            return 0.5
        try:
            value = float(match.group(0))
        except ValueError:  # pragma: no cover (regex guarantees this)
            return 0.5
        return _clamp_unit(value)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _call_kwargs(
        self,
        *,
        max_tokens: int | None,
        temperature: float | None,
        stop: list[str] | None = None,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {}
        effective_temp = temperature if temperature is not None else self._default_temperature
        if effective_temp is not None:
            kwargs["temperature"] = effective_temp
        # Anthropic requires ``max_tokens`` on every request; the per-call
        # value wins, then the client-wide default. The constructor only
        # rejects negatives — ``0`` is permitted — so this value can be
        # ``0`` when the host configured it that way; if the API rejects it,
        # the SDK surfaces the error.
        kwargs["max_tokens"] = max_tokens if max_tokens is not None else self._default_max_tokens
        if stop:
            # SDK expects ``stop_sequences`` here, not ``stop``.
            kwargs["stop_sequences"] = list(stop)
        return kwargs


# ---------------------------------------------------------------------------
# Helpers + error type
# ---------------------------------------------------------------------------


class AnthropicClientError(RuntimeError):
    """Raised for misconfiguration or unparseable responses.

    Distinct from :class:`anthropic.AnthropicError` (which we let
    bubble for network / 5xx / auth failures) so callers can treat
    configuration bugs as fatal at startup without catching every
    transient wire error.
    """


def _split_system(
    messages: list[dict[str, Any]],
) -> tuple[str | list[dict[str, Any]] | None, list[dict[str, Any]]]:
    """Split OpenAI-style messages into (system_prompt, non_system).

    Anthropic puts the system instruction at the top level of
    ``messages.create`` rather than as a row with ``role: "system"``.
    Hosts that work with the OpenAI / chat-style mixed list keep
    working unchanged; multiple system rows are concatenated so
    layered policy (e.g. tenant policy + concern advice) is preserved.

    Returns
    -------
    ``(None, conversation)`` when there are no system rows so callers
    can omit the kwarg from the wire.

    ``(joined_string, conversation)`` when every system row is a
    plain string — the parts are joined with blank lines.

    ``(blocks, conversation)`` when at least one system row is a
    list of Anthropic content blocks (``[{"type": "text", ...}]``).
    String parts are promoted to text blocks and every block is
    preserved verbatim — including ``cache_control`` markers used
    for prompt caching, citations metadata, and other block-level
    fields that would be lost if we collapsed everything to a
    string (Codex P2 on PR-8).
    """
    system_parts: list[str | list[dict[str, Any]] | dict[str, Any]] = []
    conversation: list[dict[str, Any]] = []
    for msg in messages:
        if msg.get("role") == "system":
            content = msg.get("content")
            if content is None or content == "":
                # Skip empty rows so they don't pollute the joined
                # output; an empty string round-trips as a no-op.
                continue
            system_parts.append(content)
            continue
        conversation.append(msg)

    if not system_parts:
        return (None, conversation)

    # If any part is block-form, hoist everything to blocks so the
    # block-level metadata (cache_control, citations, …) survives
    # alongside any plain-string parts the caller layered in.
    has_blocks = any(isinstance(part, list | dict) for part in system_parts)
    if has_blocks:
        flattened: list[dict[str, Any]] = []
        for part in system_parts:
            if isinstance(part, str):
                flattened.append({"type": "text", "text": part})
            elif isinstance(part, list):
                for block in part:
                    if isinstance(block, dict):
                        flattened.append(block)
            elif isinstance(part, dict):
                # Single-block shorthand: ``content={"type":"text",…}``.
                flattened.append(part)
        return (flattened, conversation)

    # All-string fast path.
    return ("\n\n".join(part for part in system_parts if isinstance(part, str)), conversation)


def _extract_text(response: Any) -> str:
    """Pull text out of an Anthropic ``Message`` response.

    ``response.content`` is a list of content blocks; we concatenate
    every block whose ``type == "text"``. Non-text blocks (tool_use,
    image, …) are skipped. Returns ``""`` when the response has no
    text channel — :meth:`score` falls back to 0.5 in that case
    rather than crashing the turn.
    """
    try:
        blocks = response.content
    except AttributeError:
        return ""
    if not blocks:
        return ""
    parts: list[str] = []
    for block in blocks:
        if getattr(block, "type", None) == "text":
            text = getattr(block, "text", None)
            if text:
                parts.append(str(text))
    return "".join(parts)


def _extract_tool_input(response: Any, tool_name: str) -> dict[str, Any] | None:
    """Find the first tool_use block matching ``tool_name`` and return its input.

    ``None`` if there isn't one, so the caller can raise a
    descriptive error rather than this helper papering over a model
    refusal.
    """
    try:
        blocks = response.content
    except AttributeError:
        return None
    if not blocks:
        return None
    for block in blocks:
        if getattr(block, "type", None) != "tool_use":
            continue
        if getattr(block, "name", None) != tool_name:
            continue
        payload = getattr(block, "input", None)
        if isinstance(payload, dict):
            # Defensive copy so the caller can't mutate the SDK's
            # internal state by accident.
            return dict(payload)
        return None
    return None


def _clamp_unit(value: float) -> float:
    if value != value:  # NaN
        return 0.5
    if value <= 0.0:
        return 0.0
    if value >= 1.0:
        return 1.0
    return float(value)


__all__ = ["AnthropicClientError", "AnthropicLLMClient"]
