"""Runtime configuration objects.

These mirror the shape of the daemon ``default.yaml`` (see
``packages/opencoat-runtime-daemon/opencoat_runtime_daemon/config/default.yaml``).
Keep them framework-free so the core remains importable without the daemon.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RuntimeBudgets(BaseModel):
    """Hard caps applied by the coordinator and weaver."""

    model_config = ConfigDict(extra="forbid")

    max_active_concerns: int = Field(default=12, ge=1)
    max_injection_tokens: int = Field(default=800, ge=1)
    max_advice_per_concern: int = Field(default=2, ge=1)


class RuntimeLoops(BaseModel):
    model_config = ConfigDict(extra="forbid")

    heartbeat_interval_seconds: float = Field(default=30.0, gt=0.0)


class RuntimeConfig(BaseModel):
    """Top-level runtime configuration.

    The core reads the fields it needs; the daemon owns transport / storage /
    LLM configuration in a separate, layered config object.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "0.2"
    loops: RuntimeLoops = Field(default_factory=RuntimeLoops)
    budgets: RuntimeBudgets = Field(default_factory=RuntimeBudgets)
