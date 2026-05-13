"""Layered config loader.

Precedence (high → low):

    CLI flags  >  environment (OPENCOAT_*)  >  user config file  >  bundled default

The loader returns a strongly-typed :class:`DaemonConfig` that bundles the
runtime config and the operational settings (storage / LLM / IPC).
"""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml
from opencoat_runtime_core.config import RuntimeConfig
from pydantic import BaseModel, ConfigDict, Field


class StorageBackend(BaseModel):
    model_config = ConfigDict(extra="allow")
    kind: str


class StorageSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    concern_store: StorageBackend = StorageBackend(kind="memory")
    dcn_store: StorageBackend = StorageBackend(kind="memory")


class LLMSettings(BaseModel):
    model_config = ConfigDict(extra="allow")
    # Default ``auto`` so a zero-config daemon picks the operator's
    # real provider whenever one is available, and only falls back to
    # stub (with a loud warning) when no credentials are present. See
    # :func:`opencoat_runtime_daemon.runtime_builder._build_auto` for
    # the probe order.
    provider: str = "auto"
    timeout_seconds: float = 20.0


class IPCEndpoint(BaseModel):
    model_config = ConfigDict(extra="allow")
    enabled: bool = False


class IPCSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    inproc: IPCEndpoint = IPCEndpoint(enabled=True)
    unix_socket: IPCEndpoint = IPCEndpoint(enabled=False)
    http: IPCEndpoint = IPCEndpoint(enabled=False)
    grpc: IPCEndpoint = IPCEndpoint(enabled=False)


class ObservabilitySettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    log_level: str = "INFO"
    otel_endpoint: str | None = None


class PluginSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hosts: list[str] = Field(default_factory=list)
    matchers: list[str] = Field(default_factory=list)
    advisors: list[str] = Field(default_factory=list)


class DaemonConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    ipc: IPCSettings = Field(default_factory=IPCSettings)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)
    plugins: PluginSettings = Field(default_factory=PluginSettings)


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_config(path: Path | None = None) -> DaemonConfig:
    """Load and validate the daemon config.

    Always starts from the bundled ``default.yaml`` and overlays the user's
    file (if any) on top.  Env / CLI overlays land at M4.
    """
    bundled = files("opencoat_runtime_daemon.config").joinpath("default.yaml").read_text()
    data: dict[str, Any] = yaml.safe_load(bundled) or {}

    if path is not None:
        user = _read_yaml(Path(path))
        data = _merge(data, user)

    return DaemonConfig.model_validate(data)


def _merge(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Recursive dict overlay — ``b`` wins on conflict."""
    out = dict(a)
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out
