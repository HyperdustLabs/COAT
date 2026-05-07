"""The 11 advice types used by the runtime (v0.1 §14.2)."""

from __future__ import annotations

from COAT_runtime_protocol import AdviceType

ADVICE_TYPES: tuple[AdviceType, ...] = tuple(AdviceType)
"""Stable, ordered tuple of all advice types — useful for UI and tests."""

__all__ = ["ADVICE_TYPES", "AdviceType"]
