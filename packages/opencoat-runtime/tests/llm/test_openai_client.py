"""Hermetic tests for :class:`OpenAILLMClient`.

The OpenAI SDK is mocked at ``openai.OpenAI`` so these tests never hit
the network. We pin:

* the four :class:`LLMClient` methods produce the expected SDK calls
  with the expected kwargs (model, messages, temperature, max_tokens,
  stop, response_format),
* the bookkeeping helpers behave (``score`` parses + clamps, the
  factories surface SDK-import / missing-key errors as
  :class:`OpenAIClientError`),
* the structural :class:`LLMClient` protocol holds, so the runtime
  will accept the adapter without further coercion.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import MagicMock, patch

import pytest
from opencoat_runtime_core.ports import LLMClient
from opencoat_runtime_llm import OpenAIClientError, OpenAILLMClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_response(text: str) -> SimpleNamespace:
    """Build a minimal stand-in for the SDK's chat.completions response."""
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
    )


def _build_client(*, reply: str = "ok") -> tuple[OpenAILLMClient, MagicMock]:
    """Construct an :class:`OpenAILLMClient` with a mocked SDK.

    Returns ``(client, mock_create)`` so tests can introspect the
    arguments the adapter passed down to
    ``chat.completions.create``.
    """
    mock_create = MagicMock(return_value=_fake_response(reply))
    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=mock_create))
    )
    fake_OpenAI = MagicMock(return_value=fake_client)

    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}, clear=False),
        patch("openai.OpenAI", fake_OpenAI),
    ):
        client = OpenAILLMClient()
    # We only return the create() mock — the constructor is asserted
    # separately when needed.
    return client, mock_create


# ---------------------------------------------------------------------------
# Construction / configuration
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_uses_explicit_api_key_over_env(self) -> None:
        fake_OpenAI = MagicMock()
        with (
            patch.dict("os.environ", {"OPENAI_API_KEY": "from-env"}, clear=False),
            patch("openai.OpenAI", fake_OpenAI),
        ):
            OpenAILLMClient(api_key="explicit")

        # Explicit kwarg must win.
        assert fake_OpenAI.call_args.kwargs["api_key"] == "explicit"

    def test_falls_back_to_env_api_key(self) -> None:
        fake_OpenAI = MagicMock()
        with (
            patch.dict("os.environ", {"OPENAI_API_KEY": "from-env"}, clear=False),
            patch("openai.OpenAI", fake_OpenAI),
        ):
            OpenAILLMClient()

        assert fake_OpenAI.call_args.kwargs["api_key"] == "from-env"

    def test_missing_api_key_raises_client_error(self) -> None:
        with (
            patch.dict("os.environ", {}, clear=True),
            pytest.raises(OpenAIClientError, match="OPENAI_API_KEY"),
        ):
            OpenAILLMClient()

    def test_forwards_base_url_and_org(self) -> None:
        fake_OpenAI = MagicMock()
        with (
            patch.dict("os.environ", {"OPENAI_API_KEY": "k"}, clear=False),
            patch("openai.OpenAI", fake_OpenAI),
        ):
            OpenAILLMClient(
                base_url="https://gateway.example.com/v1",
                organization="org-x",
                project="proj-y",
                timeout_seconds=7.0,
            )
        kwargs = fake_OpenAI.call_args.kwargs
        assert kwargs["base_url"] == "https://gateway.example.com/v1"
        assert kwargs["organization"] == "org-x"
        assert kwargs["project"] == "proj-y"
        assert kwargs["timeout"] == 7.0

    def test_missing_sdk_raises_with_install_hint(self) -> None:
        # Simulate ``import openai`` failing the way it would in a
        # deployment that didn't install the optional extra.
        with (
            patch.dict("os.environ", {"OPENAI_API_KEY": "k"}, clear=False),
            patch.dict("sys.modules", {"openai": None}),
            pytest.raises(OpenAIClientError, match="openai"),
        ):
            OpenAILLMClient()

    def test_satisfies_llm_client_protocol(self) -> None:
        client, _ = _build_client()
        assert isinstance(client, LLMClient)


# ---------------------------------------------------------------------------
# complete()
# ---------------------------------------------------------------------------


class TestComplete:
    def test_dispatches_via_chat_completions(self) -> None:
        client, mock_create = _build_client(reply="hi there")
        result = client.complete("hello")
        assert result == "hi there"
        kwargs = mock_create.call_args.kwargs
        assert kwargs["model"] == OpenAILLMClient.DEFAULT_MODEL
        # Single user message — the protocol's prompt-completion shape.
        assert kwargs["messages"] == [{"role": "user", "content": "hello"}]

    def test_forwards_max_tokens_temperature_stop(self) -> None:
        client, mock_create = _build_client()
        client.complete("hi", max_tokens=42, temperature=0.7, stop=["\n", "###"])
        kwargs = mock_create.call_args.kwargs
        assert kwargs["max_tokens"] == 42
        assert kwargs["temperature"] == 0.7
        assert kwargs["stop"] == ["\n", "###"]

    def test_omits_max_tokens_when_default_is_none(self) -> None:
        # ``default_max_tokens=None`` lets the SDK / model pick. We
        # must NOT pass ``max_tokens=None`` down — the SDK would 400.
        client, mock_create = _build_client()
        client.complete("hi")
        assert "max_tokens" not in mock_create.call_args.kwargs

    def test_default_temperature_is_deterministic(self) -> None:
        client, mock_create = _build_client()
        client.complete("hi")
        # Default 0.0 — keeps the verifier deterministic without
        # callers needing to remember to pass it.
        assert mock_create.call_args.kwargs["temperature"] == 0.0


# ---------------------------------------------------------------------------
# chat()
# ---------------------------------------------------------------------------


class TestChat:
    def test_passes_messages_through_unchanged(self) -> None:
        client, mock_create = _build_client(reply="reply!")
        msgs = [
            {"role": "system", "content": "be brief"},
            {"role": "user", "content": "hi"},
        ]
        out = client.chat(msgs)
        assert out == "reply!"
        assert mock_create.call_args.kwargs["messages"] == msgs


# ---------------------------------------------------------------------------
# structured()
# ---------------------------------------------------------------------------


class TestStructured:
    SCHEMA: ClassVar[dict] = {
        "type": "object",
        "properties": {"x": {"type": "integer"}},
        "required": ["x"],
    }

    def test_uses_json_schema_response_format(self) -> None:
        client, mock_create = _build_client(reply='{"x": 7}')
        out = client.structured([{"role": "user", "content": "give me x"}], schema=self.SCHEMA)
        assert out == {"x": 7}

        rf = mock_create.call_args.kwargs["response_format"]
        assert rf["type"] == "json_schema"
        assert rf["json_schema"]["schema"] == self.SCHEMA
        assert rf["json_schema"]["strict"] is False

    def test_empty_response_raises(self) -> None:
        client, _ = _build_client(reply="")
        with pytest.raises(OpenAIClientError, match="empty completion"):
            client.structured([{"role": "user", "content": "x"}], schema=self.SCHEMA)

    def test_invalid_json_response_raises(self) -> None:
        client, _ = _build_client(reply="not-json")
        with pytest.raises(OpenAIClientError, match="not valid JSON"):
            client.structured([{"role": "user", "content": "x"}], schema=self.SCHEMA)

    def test_round_trips_complex_payload(self) -> None:
        payload = {"items": [1, 2, 3], "meta": {"ok": True}}
        client, _ = _build_client(reply=json.dumps(payload))
        out = client.structured([{"role": "user", "content": "x"}], schema=self.SCHEMA)
        assert out == payload


# ---------------------------------------------------------------------------
# score()
# ---------------------------------------------------------------------------


class TestScore:
    def test_parses_bare_number(self) -> None:
        client, _ = _build_client(reply="0.83")
        assert client.score("p", "c") == pytest.approx(0.83)

    def test_extracts_first_number_in_messy_reply(self) -> None:
        client, _ = _build_client(reply="I'd say 0.42 because it's mid")
        assert client.score("p", "c") == pytest.approx(0.42)

    def test_clamps_above_one(self) -> None:
        client, _ = _build_client(reply="1.7")
        assert client.score("p", "c") == 1.0

    def test_clamps_below_zero(self) -> None:
        client, _ = _build_client(reply="-0.2")
        assert client.score("p", "c") == 0.0

    def test_unparseable_falls_back_to_neutral(self) -> None:
        client, _ = _build_client(reply="no way to parse this 🌀")
        assert client.score("p", "c") == 0.5

    def test_passes_criteria_into_system_prompt(self) -> None:
        client, mock_create = _build_client(reply="0.5")
        client.score("p", "c", criteria="be concise")

        kwargs = mock_create.call_args.kwargs
        # System prompt is the first message; criteria must appear
        # there so the model conditions on it.
        system = kwargs["messages"][0]
        assert system["role"] == "system"
        assert "be concise" in system["content"]
        # Score is deterministic by contract.
        assert kwargs["temperature"] == 0.0

    # --- Codex P2 regressions: scientific notation -----------------------

    def test_parses_scientific_notation_low(self) -> None:
        # Reasoning models commonly reply in exponent form for
        # near-zero scores. Without exponent support the parser would
        # truncate "1e-2" to "1" and clamp it to 1.0 — flipping a
        # near-zero score into a maximum score.
        client, _ = _build_client(reply="1e-2")
        assert client.score("p", "c") == pytest.approx(0.01)

    def test_parses_uppercase_exponent(self) -> None:
        client, _ = _build_client(reply="5E-1")
        assert client.score("p", "c") == pytest.approx(0.5)

    def test_parses_signed_exponent_with_decimal(self) -> None:
        client, _ = _build_client(reply="1.5e+3 should clamp")
        # Way above 1.0 → clamped, but the parse must consume the
        # whole exponent or we'd get 1.5 instead of 1500 → both clamp
        # to 1.0, so this is also a correctness pin.
        assert client.score("p", "c") == 1.0

    def test_does_not_pick_up_dotted_version_string(self) -> None:
        # "1.0.2" must still match "1.0" (regex stops at the second
        # dot). Without this regression the float parse would crash.
        client, _ = _build_client(reply="version 1.0.2")
        assert client.score("p", "c") == pytest.approx(1.0)

    # --- Codex P1 regressions: configurable score_max_tokens -------------

    def test_default_score_max_tokens_is_eight(self) -> None:
        client, mock_create = _build_client(reply="0.5")
        client.score("p", "c")
        assert mock_create.call_args.kwargs["max_tokens"] == 8

    def test_score_max_tokens_can_be_overridden(self) -> None:
        # Constructing with a higher cap is the workaround for
        # providers that need more headroom (verbose models, custom
        # gateways that count differently).
        mock_create = MagicMock(return_value=_fake_response("0.5"))
        fake_client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=mock_create))
        )
        with (
            patch.dict("os.environ", {"OPENAI_API_KEY": "k"}, clear=False),
            patch("openai.OpenAI", MagicMock(return_value=fake_client)),
        ):
            client = OpenAILLMClient(score_max_tokens=64)
        client.score("p", "c")
        assert mock_create.call_args.kwargs["max_tokens"] == 64

    def test_score_max_tokens_none_omits_max_tokens_kwarg(self) -> None:
        # Codex P1 on PR-7: OpenAI reasoning models (o1 / o3 / gpt-5
        # family) reject ``max_tokens`` outright — they want
        # ``max_completion_tokens``. Setting ``score_max_tokens=None``
        # MUST result in NO ``max_tokens`` kwarg reaching the SDK,
        # otherwise score() is unusable on those models. Critically
        # this also means we must NOT silently fall back to
        # ``default_max_tokens`` (which is what the previous
        # ``self.chat()`` plumbing did).
        mock_create = MagicMock(return_value=_fake_response("0.5"))
        fake_client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=mock_create))
        )
        with (
            patch.dict("os.environ", {"OPENAI_API_KEY": "k"}, clear=False),
            patch("openai.OpenAI", MagicMock(return_value=fake_client)),
        ):
            client = OpenAILLMClient(
                score_max_tokens=None,
                # Deliberately set a host-wide cap to prove score()
                # ignores it once the score-specific knob is None.
                default_max_tokens=200,
            )
        client.score("p", "c")
        assert "max_tokens" not in mock_create.call_args.kwargs

    def test_score_does_not_inherit_default_temperature(self) -> None:
        # Even when the host wires a high default temperature for
        # creative work elsewhere, score() must stay deterministic.
        mock_create = MagicMock(return_value=_fake_response("0.5"))
        fake_client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=mock_create))
        )
        with (
            patch.dict("os.environ", {"OPENAI_API_KEY": "k"}, clear=False),
            patch("openai.OpenAI", MagicMock(return_value=fake_client)),
        ):
            client = OpenAILLMClient(default_temperature=0.9)
        client.score("p", "c")
        assert mock_create.call_args.kwargs["temperature"] == 0.0
