"""Build a wired :class:`COATRuntime` from a :class:`DaemonConfig` (M4 PR-17).

The daemon, the CLI's in-proc smoke harness, and every later M4 IPC
endpoint all want the **same** runtime out of the same config — so we
keep that wiring in one place instead of letting it drift between
``daemon.py``, ``__main__.py``, and the host examples.

Inputs (high → low precedence):

1. ``DaemonConfig`` — typed, already overlaid with the user's YAML.
2. ``env`` — process environment mapping (defaults to :data:`os.environ`)
   used **only** for LLM provider credentials. Storage paths come
   from the config, not the env.

Outputs:

* :class:`BuiltRuntime` — bundles the live :class:`COATRuntime`, the
  resolved provider label, and a ``close()`` callable the caller invokes
  on shutdown so sqlite connections aren't leaked. The future
  :class:`~COAT_runtime_daemon.daemon.Daemon` calls this at startup and
  routes ``close()`` from its drain handler.

Supported backends in this PR:

* Storage: ``memory`` (default) and ``sqlite`` (``path:`` field on the
  backend block). Both stores accept ``:memory:`` and treat the empty
  / missing path as in-memory.
* LLM: ``stub`` (default), plus ``openai`` / ``anthropic`` / ``azure``
  via the same lazy import path used in
  :mod:`examples.02_coding_agent_demo.llm`. Real-provider construction
  is hermetic in CI because the providers' SDKs are only imported when
  the matching ``provider`` is chosen.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from COAT_runtime_core import COATRuntime
from COAT_runtime_core.llm import StubLLMClient
from COAT_runtime_core.ports import ConcernStore, DCNStore, LLMClient
from COAT_runtime_storage.memory import MemoryConcernStore, MemoryDCNStore
from COAT_runtime_storage.sqlite import SqliteConcernStore, SqliteDCNStore

from .config.loader import DaemonConfig, LLMSettings, StorageBackend

_STUB_DEFAULT_CHAT = (
    "(stub) COAT daemon runtime is wired up. Set OPENAI_API_KEY / "
    "ANTHROPIC_API_KEY / AZURE_OPENAI_ENDPOINT (and friends) and "
    "switch the daemon's llm.provider to a real provider to see a "
    "real answer here. See https://docs.python.org/3/ [1]."
)

_DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
_DEFAULT_ANTHROPIC_MODEL = "claude-3-5-haiku-latest"
_DEFAULT_AZURE_API_VERSION = "2024-10-21"


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------


@dataclass
class BuiltRuntime:
    """Configured :class:`COATRuntime` plus the resources backing it.

    ``close()`` is idempotent and closes any sqlite handles that the
    builder opened. Memory backends ignore it.
    """

    runtime: COATRuntime
    llm_label: str
    closers: list[Callable[[], None]] = field(default_factory=list)
    _closed: bool = False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for fn in self.closers:
            fn()

    def __enter__(self) -> BuiltRuntime:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def build_runtime(
    config: DaemonConfig,
    *,
    env: Mapping[str, str] | None = None,
) -> BuiltRuntime:
    """Construct a :class:`COATRuntime` wired per ``config``.

    When ``env`` is left as ``None`` the builder resolves credentials and
    optional knobs from :data:`os.environ` and lets each provider SDK
    consult its own documented env fallbacks for anything we don't pass
    through.

    When the caller passes ``env`` explicitly, the builder treats that
    mapping as the **only** environment source: credentials missing from
    both the config and the injected mapping raise loudly instead of
    silently falling back to :data:`os.environ`. This keeps tests and
    embedded uses hermetic (Codex P1 on PR-17).
    """
    env_explicit = env is not None
    resolved_env: Mapping[str, str] = env if env is not None else os.environ
    closers: list[Callable[[], None]] = []

    concern_store = _build_concern_store(config.storage.concern_store, closers)
    dcn_store = _build_dcn_store(config.storage.dcn_store, closers)
    llm, label = _build_llm(config.llm, resolved_env, env_explicit=env_explicit)

    runtime = COATRuntime(
        config.runtime,
        concern_store=concern_store,
        dcn_store=dcn_store,
        llm=llm,
    )
    return BuiltRuntime(runtime=runtime, llm_label=label, closers=closers)


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


def _backend_extras(spec: StorageBackend) -> dict[str, Any]:
    return spec.model_dump(exclude={"kind"})


def _resolve_sqlite_path(extras: dict[str, Any]) -> str:
    raw = extras.get("path")
    if raw is None or raw == "" or raw == ":memory:":
        return ":memory:"
    return str(Path(raw).expanduser())


def _build_concern_store(
    spec: StorageBackend,
    closers: list[Callable[[], None]],
) -> ConcernStore:
    kind = spec.kind.lower()
    if kind == "memory":
        return MemoryConcernStore()
    if kind == "sqlite":
        store = SqliteConcernStore(_resolve_sqlite_path(_backend_extras(spec)))
        closers.append(store.close)
        return store
    raise ValueError(f"Unknown concern_store backend kind={spec.kind!r}")


def _build_dcn_store(
    spec: StorageBackend,
    closers: list[Callable[[], None]],
) -> DCNStore:
    kind = spec.kind.lower()
    if kind == "memory":
        return MemoryDCNStore()
    if kind == "sqlite":
        store = SqliteDCNStore(_resolve_sqlite_path(_backend_extras(spec)))
        closers.append(store.close)
        return store
    raise ValueError(f"Unknown dcn_store backend kind={spec.kind!r}")


# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------


_LlmBuilder = Callable[
    [LLMSettings, Mapping[str, str], bool],
    "tuple[LLMClient, str]",
]


def _build_stub(
    _settings: LLMSettings,
    _env: Mapping[str, str],
    _env_explicit: bool,
) -> tuple[LLMClient, str]:
    return StubLLMClient(default_chat=_STUB_DEFAULT_CHAT), "stub"


def _llm_extras(settings: LLMSettings) -> dict[str, Any]:
    return settings.model_dump(exclude={"provider", "timeout_seconds"})


def _require_explicit(
    provider: str,
    field_name: str,
    env_var: str,
    *,
    env_explicit: bool,
) -> None:
    """Raise when ``env`` was passed explicitly but a required credential is missing.

    Codex P1 on PR-17: passing ``api_key=None`` (etc.) to the underlying
    SDK lets it transparently consult :data:`os.environ`, which breaks
    the hermetic ``env=`` contract callers explicitly opted into.
    """
    if not env_explicit:
        return
    raise RuntimeError(
        f"llm.provider={provider} but {field_name!r} is missing from both "
        f"the daemon config and the injected env mapping (looked for "
        f"{env_var}). Refusing to fall back to os.environ because "
        f"build_runtime(env=...) was passed explicitly."
    )


def _build_openai(
    settings: LLMSettings,
    env: Mapping[str, str],
    env_explicit: bool,
) -> tuple[LLMClient, str]:
    from COAT_runtime_llm import OpenAILLMClient

    extras = _llm_extras(settings)
    model = extras.get("model") or env.get("OPENAI_MODEL") or _DEFAULT_OPENAI_MODEL
    api_key = extras.get("api_key") or env.get("OPENAI_API_KEY")
    if not api_key:
        _require_explicit("openai", "api_key", "OPENAI_API_KEY", env_explicit=env_explicit)
    base_url = extras.get("base_url") or env.get("OPENAI_BASE_URL") or env.get("OPENAI_API_BASE")
    return (
        OpenAILLMClient(
            model=model,
            api_key=api_key,
            base_url=base_url,
            timeout_seconds=settings.timeout_seconds,
        ),
        f"openai/{model}",
    )


def _build_anthropic(
    settings: LLMSettings,
    env: Mapping[str, str],
    env_explicit: bool,
) -> tuple[LLMClient, str]:
    from COAT_runtime_llm import AnthropicLLMClient

    extras = _llm_extras(settings)
    model = extras.get("model") or env.get("ANTHROPIC_MODEL") or _DEFAULT_ANTHROPIC_MODEL
    api_key = extras.get("api_key") or env.get("ANTHROPIC_API_KEY")
    if not api_key:
        _require_explicit("anthropic", "api_key", "ANTHROPIC_API_KEY", env_explicit=env_explicit)
    base_url = extras.get("base_url") or env.get("ANTHROPIC_BASE_URL")
    return (
        AnthropicLLMClient(
            model=model,
            api_key=api_key,
            base_url=base_url,
            timeout_seconds=settings.timeout_seconds,
        ),
        f"anthropic/{model}",
    )


def _build_azure(
    settings: LLMSettings,
    env: Mapping[str, str],
    env_explicit: bool,
) -> tuple[LLMClient, str]:
    from COAT_runtime_llm import AzureOpenAILLMClient

    extras = _llm_extras(settings)
    deployment = (
        extras.get("deployment")
        or env.get("AZURE_OPENAI_DEPLOYMENT")
        or env.get("COATR_AZURE_DEPLOYMENT")
    )
    if not deployment:
        raise RuntimeError(
            "llm.provider=azure but no deployment configured. Set "
            "llm.deployment in the daemon config or AZURE_OPENAI_DEPLOYMENT "
            "in the environment."
        )

    endpoint = extras.get("endpoint") or env.get("AZURE_OPENAI_ENDPOINT")
    if not endpoint:
        _require_explicit("azure", "endpoint", "AZURE_OPENAI_ENDPOINT", env_explicit=env_explicit)
    api_key = extras.get("api_key") or env.get("AZURE_OPENAI_API_KEY")
    if not api_key:
        _require_explicit("azure", "api_key", "AZURE_OPENAI_API_KEY", env_explicit=env_explicit)

    # Honour ``OPENAI_API_VERSION`` in addition to the more specific
    # ``AZURE_OPENAI_API_VERSION`` (Codex P2 on PR-17): the Azure SDK
    # documents ``OPENAI_API_VERSION`` as its fallback, and we'd
    # otherwise pin ``_DEFAULT_AZURE_API_VERSION`` even when the
    # operator already set ``OPENAI_API_VERSION`` for the broader
    # OpenAI tooling.
    api_version = (
        extras.get("api_version")
        or env.get("AZURE_OPENAI_API_VERSION")
        or env.get("OPENAI_API_VERSION")
        or _DEFAULT_AZURE_API_VERSION
    )
    return (
        AzureOpenAILLMClient(
            deployment=deployment,
            api_version=api_version,
            endpoint=endpoint,
            api_key=api_key,
            timeout_seconds=settings.timeout_seconds,
        ),
        f"azure/{deployment}",
    )


_LLM_BUILDERS: dict[str, _LlmBuilder] = {
    "stub": _build_stub,
    "openai": _build_openai,
    "anthropic": _build_anthropic,
    "azure": _build_azure,
}


def _build_llm(
    settings: LLMSettings,
    env: Mapping[str, str],
    *,
    env_explicit: bool,
) -> tuple[LLMClient, str]:
    name = settings.provider.lower()
    builder = _LLM_BUILDERS.get(name)
    if builder is None:
        raise ValueError(
            f"Unknown llm.provider={settings.provider!r}; expected one of: {sorted(_LLM_BUILDERS)}"
        )
    return builder(settings, env, env_explicit)


__all__ = ["BuiltRuntime", "build_runtime"]
