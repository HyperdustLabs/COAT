"""Hermetic tests for :class:`AzureOpenAILLMClient`.

The Azure SDK class is mocked at ``openai.AzureOpenAI`` so these
tests never hit the network. ``AzureOpenAILLMClient`` is a thin
subclass of :class:`OpenAILLMClient` — every ``LLMClient`` method
(``complete`` / ``chat`` / ``structured`` / ``score``) is inherited
verbatim. We therefore focus on the bits Azure actually changes:

* construction (deployment / endpoint / api_version resolution +
  env-var fallbacks),
* auth resolution (api_key vs AAD token vs AAD token provider, and
  the mutual-exclusion guard between them),
* the deployment name reaching the wire as ``model=`` (Azure routes
  on deployment, not model family),
* one happy-path round-trip through each inherited method to prove
  the parent's plumbing still works against the Azure SDK class.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import MagicMock, patch

import pytest
from opencoat_runtime_core.ports import LLMClient
from opencoat_runtime_llm import (
    AzureOpenAIClientError,
    AzureOpenAILLMClient,
    OpenAIClientError,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_response(text: str) -> SimpleNamespace:
    """Stand-in for the SDK's chat.completions response object."""
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
    )


def _build_client(
    *,
    reply: str = "ok",
    env: dict[str, str] | None = None,
    **client_kwargs,
) -> tuple[AzureOpenAILLMClient, MagicMock, MagicMock]:
    """Construct an :class:`AzureOpenAILLMClient` with a mocked SDK.

    Returns ``(client, mock_create, fake_AzureOpenAI)`` so tests can
    introspect both the constructor kwargs and the ``chat.completions``
    request kwargs separately.
    """
    mock_create = MagicMock(return_value=_fake_response(reply))
    fake_sdk_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=mock_create))
    )
    fake_AzureOpenAI = MagicMock(return_value=fake_sdk_client)

    base_env = {
        "AZURE_OPENAI_API_KEY": "test-key",
        "AZURE_OPENAI_ENDPOINT": "https://test.openai.azure.com",
    }
    if env is not None:
        base_env.update(env)

    defaults: dict[str, object] = {"deployment": "gpt-4o-mini-deploy"}
    defaults.update(client_kwargs)

    with (
        patch.dict("os.environ", base_env, clear=False),
        patch("openai.AzureOpenAI", fake_AzureOpenAI),
    ):
        client = AzureOpenAILLMClient(**defaults)
    return client, mock_create, fake_AzureOpenAI


# ---------------------------------------------------------------------------
# Construction / configuration
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_satisfies_llm_client_protocol(self) -> None:
        client, _, _ = _build_client()
        assert isinstance(client, LLMClient)

    def test_requires_deployment(self) -> None:
        with (
            patch.dict("os.environ", {}, clear=True),
            patch("openai.AzureOpenAI", MagicMock()),
            pytest.raises(AzureOpenAIClientError, match="deployment"),
        ):
            AzureOpenAILLMClient(deployment="", endpoint="https://x", api_key="k")

    def test_endpoint_falls_back_to_env(self) -> None:
        # AZURE_OPENAI_ENDPOINT is the canonical Azure env var; the
        # SDK reads it too, but we forward explicitly so behaviour is
        # predictable across versions.
        _, _, fake_sdk = _build_client(
            env={"AZURE_OPENAI_ENDPOINT": "https://from-env.openai.azure.com"},
            endpoint=None,
        )
        assert fake_sdk.call_args.kwargs["azure_endpoint"] == "https://from-env.openai.azure.com"

    def test_explicit_endpoint_wins_over_env(self) -> None:
        _, _, fake_sdk = _build_client(
            env={"AZURE_OPENAI_ENDPOINT": "https://from-env.openai.azure.com"},
            endpoint="https://explicit.openai.azure.com",
        )
        assert fake_sdk.call_args.kwargs["azure_endpoint"] == "https://explicit.openai.azure.com"

    def test_missing_endpoint_raises(self) -> None:
        # No AZURE_OPENAI_ENDPOINT in env, no endpoint kwarg → fail
        # fast at startup with a descriptive message.
        with (
            patch.dict("os.environ", {"AZURE_OPENAI_API_KEY": "k"}, clear=True),
            patch("openai.AzureOpenAI", MagicMock()),
            pytest.raises(AzureOpenAIClientError, match="AZURE_OPENAI_ENDPOINT"),
        ):
            AzureOpenAILLMClient(deployment="d")

    def test_api_version_default(self) -> None:
        _, _, fake_sdk = _build_client(
            env={"OPENAI_API_VERSION": ""},  # ensure env doesn't override
            api_version=None,
        )
        assert fake_sdk.call_args.kwargs["api_version"] == AzureOpenAILLMClient.DEFAULT_API_VERSION

    def test_api_version_falls_back_to_env(self) -> None:
        _, _, fake_sdk = _build_client(
            env={"OPENAI_API_VERSION": "2025-01-01"},
            api_version=None,
        )
        assert fake_sdk.call_args.kwargs["api_version"] == "2025-01-01"

    def test_explicit_api_version_wins_over_env(self) -> None:
        _, _, fake_sdk = _build_client(
            env={"OPENAI_API_VERSION": "2025-01-01"},
            api_version="2024-12-01",
        )
        assert fake_sdk.call_args.kwargs["api_version"] == "2024-12-01"

    def test_missing_sdk_raises_with_install_hint(self) -> None:
        # Simulate ``import openai`` failing the way it would in a
        # deployment that didn't install the optional extra.
        with (
            patch.dict(
                "os.environ",
                {
                    "AZURE_OPENAI_API_KEY": "k",
                    "AZURE_OPENAI_ENDPOINT": "https://x",
                },
                clear=False,
            ),
            patch.dict("sys.modules", {"openai": None}),
            pytest.raises(AzureOpenAIClientError, match="openai"),
        ):
            AzureOpenAILLMClient(deployment="d")

    def test_azure_error_is_alias_of_openai_error(self) -> None:
        # Hosts that catch ``OpenAIClientError`` keep working when
        # they switch to Azure — pin the alias relationship.
        assert AzureOpenAIClientError is OpenAIClientError


# ---------------------------------------------------------------------------
# Auth resolution
# ---------------------------------------------------------------------------


class TestAuth:
    def test_explicit_api_key_over_env(self) -> None:
        _, _, fake_sdk = _build_client(api_key="explicit")
        assert fake_sdk.call_args.kwargs["api_key"] == "explicit"

    def test_falls_back_to_env_api_key(self) -> None:
        _, _, fake_sdk = _build_client(env={"AZURE_OPENAI_API_KEY": "from-env"})
        assert fake_sdk.call_args.kwargs["api_key"] == "from-env"

    def test_missing_credential_raises(self) -> None:
        with (
            patch.dict(
                "os.environ",
                {"AZURE_OPENAI_ENDPOINT": "https://x"},
                clear=True,
            ),
            patch("openai.AzureOpenAI", MagicMock()),
            pytest.raises(AzureOpenAIClientError, match="credential"),
        ):
            AzureOpenAILLMClient(deployment="d")

    def test_aad_token_path_omits_api_key(self) -> None:
        # Pre-fetched AAD token: the SDK gets ``azure_ad_token`` and
        # ``api_key`` must be ``None`` (passing both would make the
        # request shape ambiguous).
        _, _, fake_sdk = _build_client(
            env={"AZURE_OPENAI_API_KEY": ""},
            api_key=None,
            azure_ad_token="aad-token",
        )
        kwargs = fake_sdk.call_args.kwargs
        assert kwargs["azure_ad_token"] == "aad-token"
        assert kwargs["api_key"] is None

    def test_aad_token_provider_path_forwarded(self) -> None:
        # Provider callable: SDK calls it on each request → token
        # rotation is automatic. Pin that we forward the callable
        # without invoking it ourselves.
        provider_calls: list[None] = []

        def provider() -> str:
            provider_calls.append(None)
            return "rotating-token"

        _, _, fake_sdk = _build_client(
            env={"AZURE_OPENAI_API_KEY": ""},
            api_key=None,
            azure_ad_token_provider=provider,
        )
        kwargs = fake_sdk.call_args.kwargs
        assert kwargs["azure_ad_token_provider"] is provider
        assert kwargs["api_key"] is None
        # Adapter must NOT call the provider itself; that's the SDK's
        # job at request time.
        assert provider_calls == []

    def test_api_key_and_aad_token_are_mutually_exclusive(self) -> None:
        with (
            patch.dict(
                "os.environ",
                {"AZURE_OPENAI_ENDPOINT": "https://x"},
                clear=True,
            ),
            patch("openai.AzureOpenAI", MagicMock()),
            pytest.raises(AzureOpenAIClientError, match="exactly one"),
        ):
            AzureOpenAILLMClient(
                deployment="d",
                api_key="k",
                azure_ad_token="aad",
            )

    def test_api_key_and_aad_provider_are_mutually_exclusive(self) -> None:
        with (
            patch.dict(
                "os.environ",
                {"AZURE_OPENAI_ENDPOINT": "https://x"},
                clear=True,
            ),
            patch("openai.AzureOpenAI", MagicMock()),
            pytest.raises(AzureOpenAIClientError, match="exactly one"),
        ):
            AzureOpenAILLMClient(
                deployment="d",
                api_key="k",
                azure_ad_token_provider=lambda: "t",
            )

    def test_aad_token_and_aad_provider_are_mutually_exclusive(self) -> None:
        # Codex P2 on PR-9: forwarding both a static AAD token AND a
        # token provider to AzureOpenAI makes runtime auth ambiguous —
        # the SDK can silently pin the static token instead of calling
        # the provider, which defeats token rotation. Fail fast at
        # construction.
        with (
            patch.dict(
                "os.environ",
                {"AZURE_OPENAI_ENDPOINT": "https://x"},
                clear=True,
            ),
            patch("openai.AzureOpenAI", MagicMock()),
            pytest.raises(
                AzureOpenAIClientError,
                match=r"exactly one.*azure_ad_token.*azure_ad_token_provider",
            ),
        ):
            AzureOpenAILLMClient(
                deployment="d",
                azure_ad_token="aad",
                azure_ad_token_provider=lambda: "t",
            )

    def test_all_three_auth_paths_at_once_rejected(self) -> None:
        # Belt-and-braces: the count-based guard should also catch the
        # 3-way over-specification with a single error, listing all
        # three names so the host can fix the misconfig in one go.
        with (
            patch.dict(
                "os.environ",
                {"AZURE_OPENAI_ENDPOINT": "https://x"},
                clear=True,
            ),
            patch("openai.AzureOpenAI", MagicMock()),
            pytest.raises(AzureOpenAIClientError) as excinfo,
        ):
            AzureOpenAILLMClient(
                deployment="d",
                api_key="k",
                azure_ad_token="aad",
                azure_ad_token_provider=lambda: "t",
            )
        msg = str(excinfo.value)
        assert "api_key" in msg
        assert "azure_ad_token" in msg
        assert "azure_ad_token_provider" in msg
        assert "got 3" in msg


# ---------------------------------------------------------------------------
# Deployment routing — the headline difference vs upstream OpenAI
# ---------------------------------------------------------------------------


class TestDeploymentRouting:
    def test_deployment_reaches_wire_as_model_kwarg(self) -> None:
        # Azure routes on deployment name; the parent's
        # ``chat.completions.create(model=self._model)`` plumbing
        # must therefore receive the deployment, not a model family.
        client, mock_create, _ = _build_client(deployment="my-prod-deploy")
        client.complete("hello")
        assert mock_create.call_args.kwargs["model"] == "my-prod-deploy"

    def test_deployment_property_exposes_routing_target(self) -> None:
        client, _, _ = _build_client(deployment="my-prod-deploy")
        assert client.deployment == "my-prod-deploy"

    def test_endpoint_and_api_version_properties(self) -> None:
        client, _, _ = _build_client(
            endpoint="https://my-resource.openai.azure.com",
            api_version="2024-12-01",
        )
        assert client.endpoint == "https://my-resource.openai.azure.com"
        assert client.api_version == "2024-12-01"


# ---------------------------------------------------------------------------
# Inherited LLMClient methods — one happy-path round-trip per method
# ---------------------------------------------------------------------------


class TestInheritedMethods:
    """Pin that the parent's plumbing still works once the SDK class
    has been swapped from ``OpenAI`` to ``AzureOpenAI``. We only need
    one round-trip per method here — the full per-method behaviour
    is covered exhaustively by the OpenAI tests.
    """

    SCHEMA: ClassVar[dict] = {
        "type": "object",
        "properties": {"x": {"type": "integer"}},
        "required": ["x"],
    }

    def test_complete_round_trip(self) -> None:
        client, mock_create, _ = _build_client(reply="hi there")
        assert client.complete("hello") == "hi there"
        kwargs = mock_create.call_args.kwargs
        assert kwargs["messages"] == [{"role": "user", "content": "hello"}]

    def test_chat_round_trip(self) -> None:
        client, mock_create, _ = _build_client(reply="reply!")
        msgs = [
            {"role": "system", "content": "be brief"},
            {"role": "user", "content": "hi"},
        ]
        assert client.chat(msgs) == "reply!"
        # Azure uses the same chat-completions shape as upstream — no
        # system-row hoisting, no role rewrites.
        assert mock_create.call_args.kwargs["messages"] == msgs

    def test_structured_round_trip(self) -> None:
        client, mock_create, _ = _build_client(reply='{"x": 7}')
        out = client.structured([{"role": "user", "content": "give me x"}], schema=self.SCHEMA)
        assert out == {"x": 7}
        rf = mock_create.call_args.kwargs["response_format"]
        assert rf["type"] == "json_schema"
        assert rf["json_schema"]["schema"] == self.SCHEMA

    def test_structured_invalid_json_raises(self) -> None:
        # Inherited error path — ``OpenAIClientError`` IS the Azure
        # error type (alias), so this pin doubles as a regression
        # against accidentally splitting the type hierarchy.
        client, _, _ = _build_client(reply="not-json")
        with pytest.raises(AzureOpenAIClientError, match="not valid JSON"):
            client.structured([{"role": "user", "content": "x"}], schema=self.SCHEMA)

    def test_score_round_trip(self) -> None:
        client, mock_create, _ = _build_client(reply="0.83")
        assert client.score("p", "c") == pytest.approx(0.83)
        # Score MUST reach the wire with deployment as ``model=`` — a
        # regression here would route every score() call to whatever
        # OpenAILLMClient.DEFAULT_MODEL happens to be set to.
        assert mock_create.call_args.kwargs["model"] == "gpt-4o-mini-deploy"

    def test_score_max_tokens_default_inherited(self) -> None:
        client, mock_create, _ = _build_client(reply="0.5")
        client.score("p", "c")
        assert mock_create.call_args.kwargs["max_tokens"] == 8


# ---------------------------------------------------------------------------
# Lazy import behaviour at the package level
# ---------------------------------------------------------------------------


class TestLazyExport:
    def test_top_level_lazy_import_resolves(self) -> None:
        import opencoat_runtime_llm

        assert opencoat_runtime_llm.AzureOpenAILLMClient is AzureOpenAILLMClient
        assert opencoat_runtime_llm.AzureOpenAIClientError is AzureOpenAIClientError

    def test_round_trip_through_lazy_loader_is_subclass_of_openai(self) -> None:
        # If the dispatch table ever pointed at the wrong module, the
        # subclass relationship would silently break and we'd lose
        # method inheritance — this catches that early.
        import opencoat_runtime_llm

        assert issubclass(
            opencoat_runtime_llm.AzureOpenAILLMClient,
            opencoat_runtime_llm.OpenAILLMClient,
        )


# ---------------------------------------------------------------------------
# Wire integrity — the SDK kwargs we actually send
# ---------------------------------------------------------------------------


class TestWireIntegrity:
    def test_constructor_forwards_organization_project_timeout(self) -> None:
        _, _, fake_sdk = _build_client(
            organization="org-x",
            project="proj-y",
            timeout_seconds=7.0,
        )
        kwargs = fake_sdk.call_args.kwargs
        assert kwargs["organization"] == "org-x"
        assert kwargs["project"] == "proj-y"
        assert kwargs["timeout"] == 7.0

    def test_default_temperature_is_deterministic(self) -> None:
        client, mock_create, _ = _build_client()
        client.complete("hi")
        # Inherited default — pin it so future refactors don't drop it.
        assert mock_create.call_args.kwargs["temperature"] == 0.0

    def test_structured_preserves_complex_payload(self) -> None:
        # End-to-end JSON round-trip across the schema path; Azure's
        # JSON-schema mode is identical to upstream so this should
        # just work.
        payload = {"items": [1, 2, 3], "meta": {"ok": True}}
        client, _, _ = _build_client(reply=json.dumps(payload))
        out = client.structured(
            [{"role": "user", "content": "x"}],
            schema={"type": "object"},
        )
        assert out == payload
