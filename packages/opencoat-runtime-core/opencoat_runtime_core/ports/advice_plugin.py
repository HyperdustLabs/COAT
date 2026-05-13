"""Advice generator plugin port.

The default generator lives under :mod:`opencoat_runtime_core.advice.generator`.
Plugins can override it to produce advice via templates, an external LLM,
or a domain-specific rules engine.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from opencoat_runtime_protocol import Advice, Concern

from ..types import JSON


@runtime_checkable
class AdvicePlugin(Protocol):
    def generate(self, concern: Concern, context: JSON | None = None) -> Advice: ...
