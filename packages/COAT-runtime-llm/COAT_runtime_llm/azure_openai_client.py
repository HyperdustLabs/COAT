"""Azure OpenAI :class:`LLMClient` adapter.

Third real provider on the M2 track (PR-9). Azure OpenAI exposes the
**same** ``chat.completions`` HTTP surface as the upstream OpenAI API,
so every :class:`LLMClient` method on :class:`OpenAILLMClient`
(`complete` / `chat` / `structured` / `score`) is reused verbatim.
The only thing Azure actually changes is the SDK constructor:

* a different auth shape (``api_key`` *or* an Entra / AAD token,
  optionally produced by a callable),
* mandatory ``api_version`` query param,
* ``model=`` at request time refers to the **deployment name**, not
  a model family — so we store the deployment in ``self._model`` and
  the parent's chat-completions plumbing just works.

Why a subclass and not a separate adapter
-----------------------------------------
The four ``LLMClient`` methods are identical between upstream OpenAI
and Azure OpenAI (chat completions API, JSON-schema response format,
score heuristic). Duplicating them would mean two places to fix if
either OpenAI or Codex flags a bug — see the score()/scientific-
notation regression on PR-7. Subclassing keeps the behaviour pinned
to one implementation and only carves out the bits that genuinely
differ (the SDK constructor + env-var names).

Error type
----------
We re-export :class:`OpenAIClientError` as :class:`AzureOpenAIClientError`
so callers that catch the upstream type keep working unchanged, and
hosts that want to be specific about which provider misconfigured
can match on the Azure alias.

Reference
---------
https://learn.microsoft.com/azure/ai-services/openai/reference
https://github.com/openai/openai-python — ``openai.AzureOpenAI``
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from .openai_client import OpenAIClientError, OpenAILLMClient

if TYPE_CHECKING:  # pragma: no cover — type-only
    from collections.abc import Callable


# Alias so consumers can match on a provider-specific name; Azure
# misconfigurations are still ``OpenAIClientError`` underneath.
AzureOpenAIClientError = OpenAIClientError


class AzureOpenAILLMClient(OpenAILLMClient):
    """Concrete :class:`LLMClient` backed by Azure OpenAI.

    Construct with a deployment + endpoint; all four ``LLMClient``
    methods are inherited from :class:`OpenAILLMClient` unchanged.

    Parameters
    ----------
    deployment:
        The Azure OpenAI **deployment name** — the alphanumeric label
        you chose when you deployed a model in your Azure resource.
        This is what Azure routes on; it replaces the upstream
        ``model`` parameter at request time. Required.
    endpoint:
        Resource endpoint, e.g. ``https://my-resource.openai.azure.com``.
        Falls back to ``AZURE_OPENAI_ENDPOINT`` if ``None``.
    api_version:
        Azure mandates the API version as a query parameter. Default
        ``2024-06-01`` — pin a newer one to opt into newer features.
        Falls back to ``OPENAI_API_VERSION`` env var when set
        (matches the SDK's own default lookup).
    api_key:
        Azure OpenAI API key. Falls back to ``AZURE_OPENAI_API_KEY``.
        Mutually exclusive with the AAD options below — use one
        auth path per client.
    azure_ad_token:
        A pre-fetched Microsoft Entra (AAD) token. Useful when the
        host already manages token lifetime. Mutually exclusive with
        ``api_key``.
    azure_ad_token_provider:
        Zero-arg callable returning a fresh AAD token. Preferred over
        a static ``azure_ad_token`` because the SDK calls it on each
        request, so token rotation is automatic. Typically:

        .. code-block:: python

            from azure.identity import DefaultAzureCredential, \
                get_bearer_token_provider
            cred = DefaultAzureCredential()
            provider = get_bearer_token_provider(
                cred, "https://cognitiveservices.azure.com/.default"
            )
            client = AzureOpenAILLMClient(deployment="...",
                                          endpoint="...",
                                          azure_ad_token_provider=provider)

    organization, project:
        Forwarded to the SDK constructor unchanged.
    timeout_seconds:
        Per-request timeout.
    default_temperature, default_max_tokens, score_max_tokens:
        Identical semantics to :class:`OpenAILLMClient`. ``score()``
        on Azure-deployed reasoning models (o1 / o3 / gpt-5 family)
        needs ``score_max_tokens=None`` for the same reason as on
        upstream OpenAI — the parent's score() implementation already
        honours that.
    """

    DEFAULT_API_VERSION = "2024-06-01"

    def __init__(
        self,
        *,
        deployment: str,
        endpoint: str | None = None,
        api_version: str | None = None,
        api_key: str | None = None,
        azure_ad_token: str | None = None,
        azure_ad_token_provider: Callable[[], str] | None = None,
        organization: str | None = None,
        project: str | None = None,
        timeout_seconds: float = 20.0,
        default_temperature: float | None = 0.0,
        default_max_tokens: int | None = None,
        score_max_tokens: int | None = OpenAILLMClient.DEFAULT_SCORE_MAX_TOKENS,
    ) -> None:
        # Lazy import: the same ``openai`` extra ships ``AzureOpenAI``,
        # so there's no separate Azure-only extra. Reuse the upstream
        # extra's install hint to keep the message simple.
        try:
            from openai import AzureOpenAI
        except ImportError as exc:
            raise AzureOpenAIClientError(
                "AzureOpenAILLMClient requires the optional 'openai' extra. "
                "Install it with `pip install COAT-runtime-llm[azure]` (alias "
                "for the OpenAI SDK)."
            ) from exc

        if not deployment:
            raise AzureOpenAIClientError("deployment must be a non-empty string")

        resolved_endpoint = (
            endpoint if endpoint is not None else os.environ.get("AZURE_OPENAI_ENDPOINT")
        )
        if not resolved_endpoint:
            raise AzureOpenAIClientError(
                "Azure endpoint is not configured. Pass endpoint=... or set "
                "the AZURE_OPENAI_ENDPOINT environment variable."
            )

        resolved_api_version = (
            api_version
            if api_version is not None
            else os.environ.get("OPENAI_API_VERSION") or self.DEFAULT_API_VERSION
        )

        # Auth resolution. The three options are mutually exclusive
        # at the SDK level — passing both ``api_key`` and an AAD token
        # makes the request shape ambiguous. Validate up front so the
        # failure is clear at startup, not on the first turn.
        ad_supplied = azure_ad_token is not None or azure_ad_token_provider is not None
        resolved_api_key: str | None
        if ad_supplied:
            if api_key is not None:
                raise AzureOpenAIClientError(
                    "Pass either api_key=... or one of "
                    "azure_ad_token / azure_ad_token_provider — not both."
                )
            resolved_api_key = None
        else:
            resolved_api_key = (
                api_key if api_key is not None else os.environ.get("AZURE_OPENAI_API_KEY")
            )
            if not resolved_api_key:
                raise AzureOpenAIClientError(
                    "No Azure OpenAI credential is configured. Pass one of "
                    "api_key=..., azure_ad_token=..., or "
                    "azure_ad_token_provider=..., or set "
                    "AZURE_OPENAI_API_KEY in the environment."
                )

        # We deliberately bypass ``OpenAILLMClient.__init__`` (which
        # constructs the upstream ``OpenAI`` client) and set the
        # bookkeeping fields the parent's methods expect. Azure routes
        # by deployment, so storing the deployment name in
        # ``self._model`` makes ``chat.completions.create(model=...)``
        # work without any further changes to the parent's methods.
        self._model = deployment
        self._timeout = timeout_seconds
        self._default_temperature = default_temperature
        self._default_max_tokens = default_max_tokens
        self._score_max_tokens = score_max_tokens
        self._endpoint = resolved_endpoint
        self._api_version = resolved_api_version
        self._client = AzureOpenAI(
            api_key=resolved_api_key,
            azure_ad_token=azure_ad_token,
            azure_ad_token_provider=azure_ad_token_provider,
            azure_endpoint=resolved_endpoint,
            api_version=resolved_api_version,
            organization=organization,
            project=project,
            timeout=timeout_seconds,
        )

    @property
    def deployment(self) -> str:
        """The Azure deployment name this client is pinned to."""
        return self._model

    @property
    def endpoint(self) -> str:
        """The configured Azure resource endpoint."""
        return self._endpoint

    @property
    def api_version(self) -> str:
        """The Azure API version this client requests against."""
        return self._api_version


__all__ = ["AzureOpenAIClientError", "AzureOpenAILLMClient"]
