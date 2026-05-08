"""Environment-driven LLM provider selection for the coding-agent demo.

The headline M2-defining behaviour is "this same agent runs against
OpenAI, Anthropic, or Azure — no code changes". The demo enforces
that promise by reading the host's environment and picking a
provider at boot:

==================================================  ==================
Trigger                                              Picked provider
==================================================  ==================
``COAT_DEMO_PROVIDER=stub``                          stub (forced)
``COAT_DEMO_PROVIDER=openai``                        openai
``COAT_DEMO_PROVIDER=anthropic``                     anthropic
``COAT_DEMO_PROVIDER=azure``                         azure
``OPENAI_API_KEY`` set                               openai
``ANTHROPIC_API_KEY`` set                            anthropic
``AZURE_OPENAI_ENDPOINT`` **and** a deployment set   azure
otherwise                                            stub
==================================================  ==================

CI never sets any of those vars, so the smoke tests always run
against the stub. Hosts that want a real provider just set the
matching ``*_API_KEY`` (or ``AZURE_OPENAI_ENDPOINT`` + deployment)
and re-run; the agent code does not change.

The Azure case requires *both* ``AZURE_OPENAI_ENDPOINT`` **and** a
deployment name (either ``COAT_DEMO_AZURE_DEPLOYMENT`` or
``AZURE_OPENAI_DEPLOYMENT``) before the auto-detect ladder will
promote to ``azure`` — otherwise a shell that only exports the
endpoint (common in shared CI templates that fan out to many
deployments) would crash at boot instead of falling through to
stub. An *explicit* ``COAT_DEMO_PROVIDER=azure`` (or
``provider="azure"`` argument) still raises loudly when the
deployment is missing — explicit asks deserve loud failures.

The stub's ``default_chat`` is overridden to a self-describing
message so a developer who runs the example without creds can tell
at a glance that the reply is synthetic.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping

from COAT_runtime_core.llm import StubLLMClient
from COAT_runtime_core.ports import LLMClient

# --- model defaults --------------------------------------------------------
#
# Keep the demo cheap by default. Hosts can override via env so we
# don't pin a specific SKU in code that would age badly.

_DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
_DEFAULT_ANTHROPIC_MODEL = "claude-3-5-haiku-latest"
_DEFAULT_AZURE_API_VERSION = "2024-10-21"

_STUB_DEFAULT_CHAT = (
    "(stub) The COAT runtime is wired up correctly, but no real LLM "
    "is configured. Set OPENAI_API_KEY / ANTHROPIC_API_KEY / "
    "AZURE_OPENAI_ENDPOINT (and friends) and re-run to see a real "
    "answer here. Concerns / pointcuts / weaving / verification all "
    "ran end-to-end against this stub reply. "
    "See https://docs.python.org/3/ for the language reference [1]."
)


# Builders take the *resolved* env mapping so a caller-injected
# ``env`` dict isn't silently leaked through to ``os.environ``
# during credential / deployment lookup (Codex P2 on PR-12: provider
# selection used the injected dict but client construction still
# read ``os.environ``, so test-only behaviour couldn't be reproduced
# without mutating the global environment).
_Builder = Callable[[Mapping[str, str]], "tuple[LLMClient, str]"]


def _build_stub(env: Mapping[str, str]) -> tuple[LLMClient, str]:
    return StubLLMClient(default_chat=_STUB_DEFAULT_CHAT), "stub"


def _build_openai(env: Mapping[str, str]) -> tuple[LLMClient, str]:
    # Imported lazily so the demo still loads when the openai SDK
    # isn't installed (the runtime exposes the client via a lazy
    # ``__getattr__`` on the LLM package; we mirror that here).
    from COAT_runtime_llm import OpenAILLMClient

    model = env.get("COAT_DEMO_OPENAI_MODEL", _DEFAULT_OPENAI_MODEL)
    # Plumb the api_key explicitly so the underlying client doesn't
    # silently fall back to ``os.environ`` when the caller passed a
    # custom ``env`` dict. Passing ``None`` keeps the default
    # ``os.environ`` resolution for the production path (where
    # ``env is os.environ``), so this is a no-op refactor for real
    # users.
    api_key = env.get("OPENAI_API_KEY")
    base_url = env.get("OPENAI_BASE_URL") or env.get("OPENAI_API_BASE")
    return (
        OpenAILLMClient(model=model, api_key=api_key, base_url=base_url),
        f"openai/{model}",
    )


def _build_anthropic(env: Mapping[str, str]) -> tuple[LLMClient, str]:
    from COAT_runtime_llm import AnthropicLLMClient

    model = env.get("COAT_DEMO_ANTHROPIC_MODEL", _DEFAULT_ANTHROPIC_MODEL)
    api_key = env.get("ANTHROPIC_API_KEY")
    base_url = env.get("ANTHROPIC_BASE_URL")
    return (
        AnthropicLLMClient(model=model, api_key=api_key, base_url=base_url),
        f"anthropic/{model}",
    )


def _build_azure(env: Mapping[str, str]) -> tuple[LLMClient, str]:
    from COAT_runtime_llm import AzureOpenAILLMClient

    deployment = env.get("COAT_DEMO_AZURE_DEPLOYMENT") or env.get("AZURE_OPENAI_DEPLOYMENT")
    if not deployment:
        raise RuntimeError(
            "Azure provider selected but no deployment is configured. "
            "Set COAT_DEMO_AZURE_DEPLOYMENT or AZURE_OPENAI_DEPLOYMENT "
            "to your Azure deployment name."
        )
    api_version = env.get("COAT_DEMO_AZURE_API_VERSION", _DEFAULT_AZURE_API_VERSION)
    endpoint = env.get("AZURE_OPENAI_ENDPOINT")
    api_key = env.get("AZURE_OPENAI_API_KEY")
    return (
        AzureOpenAILLMClient(
            deployment=deployment,
            api_version=api_version,
            endpoint=endpoint,
            api_key=api_key,
        ),
        f"azure/{deployment}",
    )


_BUILDERS: dict[str, _Builder] = {
    "stub": _build_stub,
    "openai": _build_openai,
    "anthropic": _build_anthropic,
    "azure": _build_azure,
}


def _auto_detect(env: Mapping[str, str]) -> str:
    """Pick a provider name from ``env`` based on which creds are present.

    The Azure branch deliberately also checks for a deployment name —
    auto-promoting to ``azure`` on endpoint alone would crash at
    boot in shells that export only the endpoint (Codex P2 on
    PR-12). Falling through to ``stub`` is the safe behaviour for
    auto-detection; an explicit ``provider="azure"`` (or
    ``COAT_DEMO_PROVIDER=azure``) still raises loudly because the
    user asked for it by name.
    """
    if env.get("OPENAI_API_KEY"):
        return "openai"
    if env.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if env.get("AZURE_OPENAI_ENDPOINT") and (
        env.get("COAT_DEMO_AZURE_DEPLOYMENT") or env.get("AZURE_OPENAI_DEPLOYMENT")
    ):
        return "azure"
    return "stub"


def select_llm(
    provider: str | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> tuple[LLMClient, str]:
    """Pick an :class:`LLMClient` for the demo and return ``(client, label)``.

    Parameters
    ----------
    provider:
        Optional explicit override. If set, must be one of the keys
        in :data:`_BUILDERS`. Ignores all environment auto-detection
        but still reads ``env`` for credential / deployment / model
        lookup.
    env:
        Optional environment mapping (defaults to ``os.environ``).
        Threaded through to the builders so test code can drive a
        full end-to-end provider construction without touching the
        process environment. Production callers leave it unset and
        get the standard ``os.environ`` behaviour.

    Returns
    -------
    ``(client, label)``:
        ``label`` is a short, human-readable identifier for the
        provider (e.g. ``"openai/gpt-4o-mini"``). The CLI prints it
        at boot so a developer can tell at a glance whether the
        demo is hitting a real LLM or the stub.

    Selection ladder (when ``provider is None``):

    1. ``COAT_DEMO_PROVIDER`` env var (one of ``stub``, ``openai``,
       ``anthropic``, ``azure``).
    2. ``OPENAI_API_KEY`` set → openai.
    3. ``ANTHROPIC_API_KEY`` set → anthropic.
    4. ``AZURE_OPENAI_ENDPOINT`` **and** a deployment name set
       → azure.  (Endpoint-only does **not** auto-promote — it
       falls through to stub.  Use an explicit ``COAT_DEMO_PROVIDER=
       azure`` if you want a loud failure on missing deployment.)
    5. Otherwise → stub.
    """
    e: Mapping[str, str] = env if env is not None else os.environ

    chosen = provider
    if chosen is None:
        chosen = e.get("COAT_DEMO_PROVIDER")
    if chosen is None:
        chosen = _auto_detect(e)

    chosen = chosen.lower()
    builder: _Builder | None = _BUILDERS.get(chosen)
    if builder is None:
        raise ValueError(f"Unknown LLM provider {chosen!r}; expected one of: {sorted(_BUILDERS)}")
    return builder(e)


__all__: list[str] = ["select_llm"]
