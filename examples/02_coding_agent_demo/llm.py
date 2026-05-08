"""Environment-driven LLM provider selection for the coding-agent demo.

The headline M2-defining behaviour is "this same agent runs against
OpenAI, Anthropic, or Azure — no code changes". The demo enforces
that promise by reading the host's environment and picking a
provider at boot:

==================================  ==================================
Trigger                              Picked provider
==================================  ==================================
``COAT_DEMO_PROVIDER=stub``          :class:`StubLLMClient` (forced)
``COAT_DEMO_PROVIDER=openai``        :class:`OpenAILLMClient`
``COAT_DEMO_PROVIDER=anthropic``     :class:`AnthropicLLMClient`
``COAT_DEMO_PROVIDER=azure``         :class:`AzureOpenAILLMClient`
``OPENAI_API_KEY`` set               :class:`OpenAILLMClient`
``ANTHROPIC_API_KEY`` set            :class:`AnthropicLLMClient`
``AZURE_OPENAI_ENDPOINT`` set        :class:`AzureOpenAILLMClient`
otherwise                            :class:`StubLLMClient`
==================================  ==================================

CI never sets any of those vars, so the smoke tests always run
against the stub. Hosts that want a real provider just set the
matching ``*_API_KEY`` (or ``AZURE_OPENAI_ENDPOINT`` + creds) and
re-run; the agent code does not change.

The stub's ``default_chat`` is overridden to a self-describing
message so a developer who runs the example without creds can tell
at a glance that the reply is synthetic.
"""

from __future__ import annotations

import os
from typing import Any

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


def _build_stub() -> tuple[LLMClient, str]:
    return StubLLMClient(default_chat=_STUB_DEFAULT_CHAT), "stub"


def _build_openai() -> tuple[LLMClient, str]:
    # Imported lazily so the demo still loads when the openai SDK
    # isn't installed (the runtime exposes the client via a lazy
    # ``__getattr__`` on the LLM package; we mirror that here).
    from COAT_runtime_llm import OpenAILLMClient

    model = os.environ.get("COAT_DEMO_OPENAI_MODEL", _DEFAULT_OPENAI_MODEL)
    return OpenAILLMClient(model=model), f"openai/{model}"


def _build_anthropic() -> tuple[LLMClient, str]:
    from COAT_runtime_llm import AnthropicLLMClient

    model = os.environ.get("COAT_DEMO_ANTHROPIC_MODEL", _DEFAULT_ANTHROPIC_MODEL)
    return AnthropicLLMClient(model=model), f"anthropic/{model}"


def _build_azure() -> tuple[LLMClient, str]:
    from COAT_runtime_llm import AzureOpenAILLMClient

    deployment = os.environ.get("COAT_DEMO_AZURE_DEPLOYMENT") or os.environ.get(
        "AZURE_OPENAI_DEPLOYMENT"
    )
    if not deployment:
        raise RuntimeError(
            "Azure provider selected but no deployment is configured. "
            "Set COAT_DEMO_AZURE_DEPLOYMENT or AZURE_OPENAI_DEPLOYMENT "
            "to your Azure deployment name."
        )
    api_version = os.environ.get("COAT_DEMO_AZURE_API_VERSION", _DEFAULT_AZURE_API_VERSION)
    return (
        AzureOpenAILLMClient(deployment=deployment, api_version=api_version),
        f"azure/{deployment}",
    )


_BUILDERS: dict[str, Any] = {
    "stub": _build_stub,
    "openai": _build_openai,
    "anthropic": _build_anthropic,
    "azure": _build_azure,
}


def select_llm(
    provider: str | None = None,
    *,
    env: dict[str, str] | None = None,
) -> tuple[LLMClient, str]:
    """Pick an :class:`LLMClient` for the demo and return ``(client, label)``.

    Parameters
    ----------
    provider:
        Optional explicit override. If set, must be one of the keys
        in :data:`_BUILDERS`. Ignores all environment auto-detection.
    env:
        Optional environment dict (defaults to ``os.environ``).
        Injected for tests so we don't pollute the real
        environment when proving the auto-detection ladder.

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
    4. ``AZURE_OPENAI_ENDPOINT`` set → azure.
    5. Otherwise → stub.
    """
    e = env if env is not None else os.environ

    chosen = provider
    if chosen is None:
        chosen = e.get("COAT_DEMO_PROVIDER")
    if chosen is None:
        if e.get("OPENAI_API_KEY"):
            chosen = "openai"
        elif e.get("ANTHROPIC_API_KEY"):
            chosen = "anthropic"
        elif e.get("AZURE_OPENAI_ENDPOINT"):
            chosen = "azure"
        else:
            chosen = "stub"

    chosen = chosen.lower()
    builder = _BUILDERS.get(chosen)
    if builder is None:
        raise ValueError(f"Unknown LLM provider {chosen!r}; expected one of: {sorted(_BUILDERS)}")
    return builder()


__all__ = ["select_llm"]
