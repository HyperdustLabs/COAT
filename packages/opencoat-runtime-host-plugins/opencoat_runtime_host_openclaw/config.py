"""OpenClaw adapter configuration."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class OpenClawAdapterConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    inject_into_runtime_prompt: bool = True
