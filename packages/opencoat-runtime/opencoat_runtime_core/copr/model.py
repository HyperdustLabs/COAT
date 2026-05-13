"""Re-exports the protocol's COPR models."""

from __future__ import annotations

from opencoat_runtime_protocol import COPR
from opencoat_runtime_protocol.envelopes import CoprMessage, CoprPromptSection, CoprSpan

__all__ = ["COPR", "CoprMessage", "CoprPromptSection", "CoprSpan"]
