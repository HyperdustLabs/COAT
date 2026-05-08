"""Hermetic tests for :class:`AnthropicLLMClient`.

The Anthropic SDK is mocked at ``anthropic.Anthropic`` so these tests
never hit the network. The provider-specific surprises pinned here:

* the ``role: "system"`` row from an OpenAI-style messages list is
  hoisted out into Anthropic's top-level ``system=`` kwarg;
* every request carries a ``max_tokens`` (Anthropic 4xxs without one)
  and the per-call value beats the client-wide default beats the
  built-in default;
* :meth:`structured` uses forced tool use rather than a JSON-schema
  ``response_format`` (which Anthropic doesn't ship);
* :meth:`score` parses a single number out of a text response with
  the same scientific-notation regex as the OpenAI adapter — and
  stays deterministic + cheap regardless of the host-wide defaults.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import MagicMock, patch

import pytest
from COAT_runtime_core.ports import LLMClient
from COAT_runtime_llm import AnthropicClientError, AnthropicLLMClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _text_block(text: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=text)


def _tool_use_block(name: str, payload: dict) -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", name=name, input=payload)


def _fake_response(*blocks: SimpleNamespace) -> SimpleNamespace:
    """Stand-in for an Anthropic ``Message`` response object.

    Anthropic responses carry a ``content`` list of typed blocks
    (text / tool_use / image / …). We pass the raw blocks the test
    cares about and let the adapter pick the right ones.
    """
    return SimpleNamespace(content=list(blocks))


def _text_response(text: str) -> SimpleNamespace:
    return _fake_response(_text_block(text))


def _build_client(
    *,
    reply: str = "ok",
    blocks: tuple[SimpleNamespace, ...] | None = None,
    **client_kwargs,
) -> tuple[AnthropicLLMClient, MagicMock]:
    """Construct an :class:`AnthropicLLMClient` with a mocked SDK.

    Returns ``(client, mock_create)`` so tests can introspect the
    arguments the adapter handed down to ``messages.create``.
    """
    response = _text_response(reply) if blocks is None else _fake_response(*blocks)
    mock_create = MagicMock(return_value=response)
    fake_client = SimpleNamespace(messages=SimpleNamespace(create=mock_create))
    fake_anthropic = MagicMock(return_value=fake_client)

    with (
        patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}, clear=False),
        patch("anthropic.Anthropic", fake_anthropic),
    ):
        client = AnthropicLLMClient(**client_kwargs)
    return client, mock_create


# ---------------------------------------------------------------------------
# Construction / configuration
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_uses_explicit_api_key_over_env(self) -> None:
        fake_anthropic = MagicMock()
        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "from-env"}, clear=False),
            patch("anthropic.Anthropic", fake_anthropic),
        ):
            AnthropicLLMClient(api_key="explicit")

        # Explicit kwarg must win.
        assert fake_anthropic.call_args.kwargs["api_key"] == "explicit"

    def test_falls_back_to_env_api_key(self) -> None:
        fake_anthropic = MagicMock()
        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "from-env"}, clear=False),
            patch("anthropic.Anthropic", fake_anthropic),
        ):
            AnthropicLLMClient()

        assert fake_anthropic.call_args.kwargs["api_key"] == "from-env"

    def test_missing_api_key_raises_client_error(self) -> None:
        with (
            patch.dict("os.environ", {}, clear=True),
            pytest.raises(AnthropicClientError, match="ANTHROPIC_API_KEY"),
        ):
            AnthropicLLMClient()

    def test_forwards_base_url_and_timeout(self) -> None:
        fake_anthropic = MagicMock()
        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "k"}, clear=False),
            patch("anthropic.Anthropic", fake_anthropic),
        ):
            AnthropicLLMClient(
                base_url="https://gateway.example.com",
                timeout_seconds=7.0,
            )
        kwargs = fake_anthropic.call_args.kwargs
        assert kwargs["base_url"] == "https://gateway.example.com"
        assert kwargs["timeout"] == 7.0

    def test_missing_sdk_raises_with_install_hint(self) -> None:
        # Simulate ``import anthropic`` failing the way it would in a
        # deployment that didn't install the optional extra.
        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "k"}, clear=False),
            patch.dict("sys.modules", {"anthropic": None}),
            pytest.raises(AnthropicClientError, match="anthropic"),
        ):
            AnthropicLLMClient()

    def test_rejects_non_positive_default_max_tokens(self) -> None:
        # Anthropic's API 400s on non-positive ``max_tokens``. Catching
        # this at construction makes the failure mode obvious instead
        # of surfacing as an opaque API error on the first turn.
        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "k"}, clear=False),
            patch("anthropic.Anthropic", MagicMock()),
            pytest.raises(AnthropicClientError, match="default_max_tokens"),
        ):
            AnthropicLLMClient(default_max_tokens=0)

    def test_rejects_non_positive_score_max_tokens(self) -> None:
        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "k"}, clear=False),
            patch("anthropic.Anthropic", MagicMock()),
            pytest.raises(AnthropicClientError, match="score_max_tokens"),
        ):
            AnthropicLLMClient(score_max_tokens=-1)

    def test_satisfies_llm_client_protocol(self) -> None:
        client, _ = _build_client()
        assert isinstance(client, LLMClient)


# ---------------------------------------------------------------------------
# complete()
# ---------------------------------------------------------------------------


class TestComplete:
    def test_dispatches_via_messages_create(self) -> None:
        client, mock_create = _build_client(reply="hi there")
        result = client.complete("hello")
        assert result == "hi there"
        kwargs = mock_create.call_args.kwargs
        assert kwargs["model"] == AnthropicLLMClient.DEFAULT_MODEL
        # Single user message — the protocol's prompt-completion shape.
        assert kwargs["messages"] == [{"role": "user", "content": "hello"}]
        # No system row was supplied, so the kwarg must NOT appear.
        # (Sending ``system=""`` to Anthropic is harmless but clutters
        # the wire and breaks a couple of OpenAI-compat gateways.)
        assert "system" not in kwargs

    def test_forwards_max_tokens_temperature_stop(self) -> None:
        client, mock_create = _build_client()
        client.complete("hi", max_tokens=42, temperature=0.7, stop=["\n", "###"])
        kwargs = mock_create.call_args.kwargs
        assert kwargs["max_tokens"] == 42
        assert kwargs["temperature"] == 0.7
        # Anthropic spells it ``stop_sequences`` — the adapter must
        # rename, not pass through.
        assert kwargs["stop_sequences"] == ["\n", "###"]
        assert "stop" not in kwargs

    def test_falls_back_to_default_max_tokens_when_unset(self) -> None:
        # Anthropic requires max_tokens, so unlike OpenAI the adapter
        # MUST supply one even when neither the call nor the host
        # passed an override.
        client, mock_create = _build_client()
        client.complete("hi")
        assert mock_create.call_args.kwargs["max_tokens"] == AnthropicLLMClient.DEFAULT_MAX_TOKENS

    def test_default_temperature_is_deterministic(self) -> None:
        client, mock_create = _build_client()
        client.complete("hi")
        assert mock_create.call_args.kwargs["temperature"] == 0.0


# ---------------------------------------------------------------------------
# chat() — system splitting is the headline behaviour change vs OpenAI
# ---------------------------------------------------------------------------


class TestChat:
    def test_splits_system_messages_to_top_level_kwarg(self) -> None:
        # Anthropic's API takes ``system=`` as a top-level kwarg and
        # rejects ``role: "system"`` entries inside ``messages``. The
        # adapter must do the split for OpenAI-style hosts so they
        # don't have to learn the wire shape.
        client, mock_create = _build_client(reply="reply!")
        msgs = [
            {"role": "system", "content": "be brief"},
            {"role": "user", "content": "hi"},
        ]
        out = client.chat(msgs)
        assert out == "reply!"
        kwargs = mock_create.call_args.kwargs
        assert kwargs["system"] == "be brief"
        # System row is gone from the conversation list.
        assert kwargs["messages"] == [{"role": "user", "content": "hi"}]

    def test_concatenates_multiple_system_messages(self) -> None:
        # Layered policy (tenant + concern + advice) commonly appears
        # as multiple system rows. Anthropic only takes one ``system=``
        # string; concat with blank lines preserves intent without
        # injecting structural markup.
        client, mock_create = _build_client()
        client.chat(
            [
                {"role": "system", "content": "policy A"},
                {"role": "user", "content": "u1"},
                {"role": "system", "content": "policy B"},
                {"role": "assistant", "content": "a1"},
            ]
        )
        kwargs = mock_create.call_args.kwargs
        assert kwargs["system"] == "policy A\n\npolicy B"
        assert kwargs["messages"] == [
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "a1"},
        ]

    def test_chat_without_system_omits_kwarg(self) -> None:
        client, mock_create = _build_client()
        client.chat([{"role": "user", "content": "hi"}])
        assert "system" not in mock_create.call_args.kwargs

    def test_extracts_text_across_multiple_text_blocks(self) -> None:
        # Some Anthropic models (and gateways) emit multi-block
        # responses. The adapter must concatenate every text block in
        # order so the host sees the full reply, not just the first
        # chunk.
        client, _ = _build_client(blocks=(_text_block("part 1 "), _text_block("part 2")))
        out = client.chat([{"role": "user", "content": "x"}])
        assert out == "part 1 part 2"

    def test_skips_non_text_blocks(self) -> None:
        # Tool_use / image blocks must not show up in the text reply.
        client, _ = _build_client(
            blocks=(
                _text_block("answer"),
                _tool_use_block("noise", {"x": 1}),
            )
        )
        out = client.chat([{"role": "user", "content": "x"}])
        assert out == "answer"

    def test_empty_response_returns_empty_string(self) -> None:
        # Fail-soft: chat() must not raise on empty responses;
        # score() depends on this to fall back to 0.5.
        client, _ = _build_client(blocks=())
        assert client.chat([{"role": "user", "content": "x"}]) == ""


# ---------------------------------------------------------------------------
# structured() — forced tool use, since Anthropic has no JSON-schema mode
# ---------------------------------------------------------------------------


class TestStructured:
    SCHEMA: ClassVar[dict] = {
        "type": "object",
        "properties": {"x": {"type": "integer"}},
        "required": ["x"],
    }

    def test_uses_forced_tool_use(self) -> None:
        # The adapter defines a single tool ``respond`` whose
        # ``input_schema`` IS the caller's schema, and pins the model
        # to it via ``tool_choice``. This is the strict-mode
        # equivalent on Anthropic — any other shape and the request
        # would 400 server-side.
        mock_create = MagicMock(return_value=_fake_response(_tool_use_block("respond", {"x": 7})))
        fake_client = SimpleNamespace(messages=SimpleNamespace(create=mock_create))
        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "k"}, clear=False),
            patch("anthropic.Anthropic", MagicMock(return_value=fake_client)),
        ):
            client = AnthropicLLMClient()
        out = client.structured(
            [{"role": "user", "content": "give me x"}],
            schema=self.SCHEMA,
        )
        assert out == {"x": 7}

        kwargs = mock_create.call_args.kwargs
        tools = kwargs["tools"]
        assert len(tools) == 1
        assert tools[0]["name"] == "respond"
        assert tools[0]["input_schema"] == self.SCHEMA
        assert kwargs["tool_choice"] == {"type": "tool", "name": "respond"}

    def test_returns_defensive_copy_of_tool_input(self) -> None:
        # Returning the SDK's internal dict would let the host mutate
        # SDK state by accident; verify we hand back a fresh dict.
        payload = {"x": 1}
        mock_create = MagicMock(return_value=_fake_response(_tool_use_block("respond", payload)))
        fake_client = SimpleNamespace(messages=SimpleNamespace(create=mock_create))
        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "k"}, clear=False),
            patch("anthropic.Anthropic", MagicMock(return_value=fake_client)),
        ):
            client = AnthropicLLMClient()
        out = client.structured([{"role": "user", "content": "x"}], schema=self.SCHEMA)
        out["x"] = 999
        # Mutating the returned dict must not poison the SDK side.
        assert payload == {"x": 1}

    def test_no_tool_use_block_raises(self) -> None:
        # If the model declines to call the forced tool (rare but
        # possible if the schema is impossible to satisfy), surface a
        # descriptive error so the host can degrade — rather than
        # returning an empty dict and looking like success.
        mock_create = MagicMock(return_value=_fake_response(_text_block("I refuse")))
        fake_client = SimpleNamespace(messages=SimpleNamespace(create=mock_create))
        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "k"}, clear=False),
            patch("anthropic.Anthropic", MagicMock(return_value=fake_client)),
        ):
            client = AnthropicLLMClient()
        with pytest.raises(AnthropicClientError, match="tool_use"):
            client.structured([{"role": "user", "content": "x"}], schema=self.SCHEMA)

    def test_ignores_text_preamble_picks_tool_use(self) -> None:
        # Some gateways still emit a leading text block before the
        # tool_use block. Walk every block instead of grabbing the
        # first one.
        mock_create = MagicMock(
            return_value=_fake_response(
                _text_block("here's your structured response:"),
                _tool_use_block("respond", {"x": 5}),
            )
        )
        fake_client = SimpleNamespace(messages=SimpleNamespace(create=mock_create))
        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "k"}, clear=False),
            patch("anthropic.Anthropic", MagicMock(return_value=fake_client)),
        ):
            client = AnthropicLLMClient()
        out = client.structured([{"role": "user", "content": "x"}], schema=self.SCHEMA)
        assert out == {"x": 5}

    def test_splits_system_for_structured(self) -> None:
        # The system-row hoist must apply to structured() too, not
        # just chat(). Otherwise schema callers that pass policy via
        # a system row would have it silently dropped.
        mock_create = MagicMock(return_value=_fake_response(_tool_use_block("respond", {"x": 1})))
        fake_client = SimpleNamespace(messages=SimpleNamespace(create=mock_create))
        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "k"}, clear=False),
            patch("anthropic.Anthropic", MagicMock(return_value=fake_client)),
        ):
            client = AnthropicLLMClient()
        client.structured(
            [
                {"role": "system", "content": "policy"},
                {"role": "user", "content": "x"},
            ],
            schema=self.SCHEMA,
        )
        kwargs = mock_create.call_args.kwargs
        assert kwargs["system"] == "policy"
        assert kwargs["messages"] == [{"role": "user", "content": "x"}]


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
        # Anthropic puts the score instruction in ``system=`` rather
        # than as a system message inside ``messages`` (which the
        # API rejects). The criteria must show up there so the model
        # conditions on it, and only the user prompt+candidate stays
        # in the messages list.
        client, mock_create = _build_client(reply="0.5")
        client.score("p", "c", criteria="be concise")

        kwargs = mock_create.call_args.kwargs
        assert "be concise" in kwargs["system"]
        assert kwargs["messages"] == [
            {"role": "user", "content": "Prompt:\np\n\nCandidate:\nc"},
        ]
        # Score is deterministic by contract.
        assert kwargs["temperature"] == 0.0

    # --- regressions: scientific notation in score replies --------------

    def test_parses_scientific_notation_low(self) -> None:
        client, _ = _build_client(reply="1e-2")
        assert client.score("p", "c") == pytest.approx(0.01)

    def test_parses_uppercase_exponent(self) -> None:
        client, _ = _build_client(reply="5E-1")
        assert client.score("p", "c") == pytest.approx(0.5)

    def test_does_not_pick_up_dotted_version_string(self) -> None:
        client, _ = _build_client(reply="version 1.0.2")
        assert client.score("p", "c") == pytest.approx(1.0)

    # --- score_max_tokens behaviour --------------------------------------

    def test_default_score_max_tokens_is_eight(self) -> None:
        client, mock_create = _build_client(reply="0.5")
        client.score("p", "c")
        assert mock_create.call_args.kwargs["max_tokens"] == 8

    def test_score_max_tokens_can_be_overridden(self) -> None:
        client, mock_create = _build_client(reply="0.5", score_max_tokens=64)
        client.score("p", "c")
        assert mock_create.call_args.kwargs["max_tokens"] == 64

    def test_score_does_not_inherit_default_max_tokens(self) -> None:
        # Even with a generous host-wide cap, score() must use the
        # tiny score-specific cap. Going through self.chat() would
        # have made this fail (it'd inherit default_max_tokens) —
        # same Codex P1 lesson as the OpenAI adapter.
        client, mock_create = _build_client(
            reply="0.5",
            default_max_tokens=4096,
        )
        client.score("p", "c")
        assert mock_create.call_args.kwargs["max_tokens"] == 8

    def test_score_does_not_inherit_default_temperature(self) -> None:
        # Even when the host wires a high default temperature for
        # creative work elsewhere, score() must stay deterministic.
        client, mock_create = _build_client(reply="0.5", default_temperature=0.9)
        client.score("p", "c")
        assert mock_create.call_args.kwargs["temperature"] == 0.0


# ---------------------------------------------------------------------------
# Lazy import behaviour at the package level
# ---------------------------------------------------------------------------


class TestLazyExport:
    def test_top_level_lazy_import_resolves(self) -> None:
        # Sanity-check that ``from COAT_runtime_llm import ...``
        # actually works for both error and client classes — the
        # __getattr__ table is the only place that wires this up.
        import COAT_runtime_llm

        assert COAT_runtime_llm.AnthropicLLMClient is AnthropicLLMClient
        assert COAT_runtime_llm.AnthropicClientError is AnthropicClientError

    def test_unknown_attribute_raises_attribute_error(self) -> None:
        import COAT_runtime_llm

        with pytest.raises(AttributeError, match="NotARealClient"):
            _ = COAT_runtime_llm.NotARealClient
