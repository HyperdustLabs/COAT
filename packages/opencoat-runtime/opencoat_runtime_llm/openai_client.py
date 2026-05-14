"""OpenAI :class:`LLMClient` adapter.

This is the first real (network-using) provider to land — M2 PR-1.
The runtime never calls the OpenAI SDK directly; everything goes
through this adapter so the rest of the codebase stays I/O-agnostic.

Design notes
------------
* **Lazy SDK import.** ``openai`` is imported inside :meth:`__init__`
  so importing this *module* never fails when the optional
  dependency is missing — only constructing an instance does. That
  keeps ``opencoat_runtime_llm`` importable in stripped-down deployments
  (e.g. an Anthropic-only host) without having to pull the OpenAI
  SDK in too.
* **Provider compatibility.** The same surface works against the
  upstream OpenAI API, Azure OpenAI (via ``base_url``), and any
  OpenAI-compatible gateway (vLLM, TogetherAI, OpenRouter, …).
  Provider-specific differences (Azure deployments, headers) live in
  dedicated subclasses.
* **Stable surface.** We use ``chat.completions.create`` rather than
  the newer ``responses.create``: the chat completions API is the
  one shared by every OpenAI-compatible provider on the market, and
  it's preserved unchanged in the SDK 2.x line. We can swap to the
  Responses API in a follow-up once the ecosystem catches up.
* **score() heuristic.** The :class:`LLMClient` port specifies
  :meth:`score` returns a ``float`` in ``[0, 1]``. OpenAI does not
  ship a native scoring endpoint; we ask the model to rate the
  candidate against the criteria, parse the first float we find, and
  clamp into the unit interval. Unparseable replies fall back to
  ``0.5`` ("no signal") rather than raising — the consumer (verifier)
  is expected to interpret the score as a soft signal.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from .base import BaseLLMClient

_LOG = logging.getLogger(__name__)

# A line-anchored float regexp would over-match on "1.0.2"-style strings;
# this picks up the first decimal-or-integer in the response so
# "Score: 0.83 because…" / "0.83" / "I'd say 0.83/1.0" all parse.
#
# The trailing ``(?:[eE][+-]?\d+)?`` group accepts scientific notation
# (Codex P2 on PR-7): without it, a low-confidence reply like ``1e-2``
# would match only the leading ``1`` and clamp to 1.0, inverting the
# model's intent. Sub-zero scores from reasoning models often come
# back in exponent form, so the parser needs to handle them natively.
_FLOAT_RE = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?")


class OpenAILLMClient(BaseLLMClient):
    """Concrete :class:`LLMClient` backed by the OpenAI Python SDK.

    Parameters
    ----------
    model:
        Default model name — used by every method unless the call site
        overrides it via the per-method ``model`` kwarg (not part of
        the port; available as a private escape hatch).
    api_key:
        Explicit API key. If ``None`` falls back to ``OPENAI_API_KEY``
        in the process environment, mirroring the SDK's own default.
        Constructing without either raises :class:`OpenAIClientError`
        so misconfiguration fails fast at runtime startup, not on the
        first turn.
    base_url:
        Override the API endpoint. Useful for OpenAI-compatible
        providers (vLLM, OpenRouter, TogetherAI) and on-prem proxies.
        ``None`` uses the SDK's default (``https://api.openai.com/v1``).
    organization, project:
        Forwarded to the SDK constructor unchanged. Both ``None`` by
        default.
    timeout_seconds:
        Per-request timeout in seconds. Applied via the SDK's
        ``timeout=`` kwarg.
    default_temperature:
        Used when a method receives ``temperature=None``. Set to
        ``None`` to let the SDK / model choose. The default ``0.0``
        prioritises determinism for the verifier and structured paths;
        callers that want creativity (advice generation in M2) pass an
        explicit value.
    default_max_tokens:
        Same idea, for ``max_tokens``. ``None`` lets the SDK decide.
    score_max_tokens:
        Token cap applied specifically to :meth:`score`. The score
        path expects a single numeric reply, so the cap is tiny by
        default to keep wire latency down. Set to ``None`` to omit
        the cap entirely — required for OpenAI reasoning models
        (o1 / o3 / gpt-5 family) which reject ``max_tokens`` and
        expect ``max_completion_tokens`` instead. The fallback path
        (None) lets a future provider-specific subclass swap in the
        right knob without changing the score contract.
    """

    DEFAULT_MODEL = "gpt-4o-mini"
    DEFAULT_SCORE_MAX_TOKENS = 8

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        api_key: str | None = None,
        base_url: str | None = None,
        organization: str | None = None,
        project: str | None = None,
        timeout_seconds: float = 20.0,
        default_temperature: float | None = 0.0,
        default_max_tokens: int | None = None,
        score_max_tokens: int | None = DEFAULT_SCORE_MAX_TOKENS,
    ) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise OpenAIClientError(
                "OpenAILLMClient requires the optional 'openai' extra. "
                "Install it with `pip install opencoat-runtime-llm[openai]`."
            ) from exc

        resolved_key = api_key if api_key is not None else os.environ.get("OPENAI_API_KEY")
        if not resolved_key:
            raise OpenAIClientError(
                "OPENAI_API_KEY is not set and no api_key was passed. "
                "Pass api_key=... explicitly or set the OPENAI_API_KEY environment variable."
            )

        self._model = model
        self._timeout = timeout_seconds
        self._default_temperature = default_temperature
        self._default_max_tokens = default_max_tokens
        self._score_max_tokens = score_max_tokens
        self._client = OpenAI(
            api_key=resolved_key,
            base_url=base_url,
            organization=organization,
            project=project,
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
        # OpenAI's classic /completions endpoint is legacy. For prompt
        # completion we use chat.completions with a single user
        # message — same outcome, fewer surprises across providers.
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
        # ``stop`` isn't on the abstract ``LLMClient.chat`` signature
        # but the SDK takes it; we accept it as an optional extension
        # so :meth:`complete` can forward it cleanly. The protocol port
        # is unchanged.
        kwargs = self._call_kwargs(max_tokens=max_tokens, temperature=temperature, stop=stop)
        response = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            **kwargs,
        )
        return _extract_chat_text(response)

    def structured(
        self,
        messages: list[dict[str, Any]],
        *,
        schema: dict[str, Any],
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        # JSON-schema ``response_format`` guides the completion. The SDK
        # rejects unknown keys, so we wrap the caller schema under the
        # ``json_schema`` envelope it expects.
        # ``strict: true`` rejects schemas where any listed ``properties``
        # key is absent from ``required`` — a rule our
        # :class:`~opencoat_runtime_core.concern.ConcernExtractor` wire
        # contract deliberately violates: top-level ``required`` is empty
        # so the model can return ``{}`` for "no concern in this span".
        # Keep ``json_schema`` for guided JSON output; use ``strict: false``
        # so the API accepts that optional-field shape (fixes OpenAI 400
        # ``Missing 'id'`` / invalid schema on ``concern.extract``).
        response_format = {
            "type": "json_schema",
            "json_schema": {"name": "response", "schema": schema, "strict": False},
        }
        kwargs = self._call_kwargs(max_tokens=max_tokens, temperature=temperature)
        response = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            response_format=response_format,
            **kwargs,
        )
        text = _extract_chat_text(response)
        if not text:
            raise OpenAIClientError("structured() received an empty completion")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise OpenAIClientError(f"structured() response was not valid JSON: {text!r}") from exc

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
        # so the per-call kwargs are exactly what we want (Codex P1 on
        # PR-7). Going through ``chat`` made ``score_max_tokens=None``
        # silently fall back to ``default_max_tokens``, which is wrong:
        # disabling the score-specific cap should not pull in an
        # unrelated host-wide cap. It also keeps the door open for a
        # provider-specific subclass to swap in ``max_completion_tokens``
        # for OpenAI's reasoning models (o1 / o3 / gpt-5 family) without
        # touching the abstract :meth:`chat` surface.
        kwargs: dict[str, Any] = {
            # Force determinism: scoring shouldn't drift between
            # otherwise-identical calls. We override a non-zero
            # ``default_temperature`` because the contract treats
            # ``score`` as a property of the (prompt, candidate) pair.
            "temperature": 0.0,
        }
        if self._score_max_tokens is not None:
            kwargs["max_tokens"] = self._score_max_tokens

        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": instruction},
                {"role": "user", "content": f"Prompt:\n{prompt}\n\nCandidate:\n{candidate}"},
            ],
            **kwargs,
        )
        text = _extract_chat_text(response)

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
        # The SDK rejects ``None`` for several of these; only forward
        # keys that the caller (or our defaults) actually set.
        kwargs: dict[str, Any] = {}
        effective_temp = temperature if temperature is not None else self._default_temperature
        if effective_temp is not None:
            kwargs["temperature"] = effective_temp
        effective_max = max_tokens if max_tokens is not None else self._default_max_tokens
        if effective_max is not None:
            kwargs["max_tokens"] = effective_max
        if stop:
            kwargs["stop"] = list(stop)
        return kwargs


# ---------------------------------------------------------------------------
# Helpers + error type
# ---------------------------------------------------------------------------


class OpenAIClientError(RuntimeError):
    """Raised for misconfiguration or unparseable responses.

    Distinct from :class:`openai.OpenAIError` (which we let bubble for
    network / 5xx / auth failures) so callers can treat configuration
    bugs as fatal at startup without catching every transient wire
    error.
    """


def _extract_chat_text(response: Any) -> str:
    """Pull the first choice's content out of a chat completion response.

    Defensive against partially-populated responses (some OpenAI-
    compatible gateways drop ``content`` on tool calls). Returns the
    empty string rather than raising so callers — especially
    :meth:`score` — degrade to a sensible fallback.
    """
    try:
        choices = response.choices
    except AttributeError:
        return ""
    if not choices:
        return ""
    message = getattr(choices[0], "message", None)
    if message is None:
        return ""
    content = getattr(message, "content", None) or ""
    return str(content)


def _clamp_unit(value: float) -> float:
    if value != value:  # NaN
        return 0.5
    if value <= 0.0:
        return 0.0
    if value >= 1.0:
        return 1.0
    return float(value)


__all__ = ["OpenAIClientError", "OpenAILLMClient"]
