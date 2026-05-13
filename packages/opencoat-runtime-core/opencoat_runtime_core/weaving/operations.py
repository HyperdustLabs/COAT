"""The 11 weaving operations (v0.1 §15.3)."""

from __future__ import annotations

from opencoat_runtime_protocol import WeavingOperation

OPERATIONS: tuple[WeavingOperation, ...] = tuple(WeavingOperation)

__all__ = ["OPERATIONS", "WeavingOperation"]
