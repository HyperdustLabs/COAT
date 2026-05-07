"""The 13 DCN relation types (v0.1 §10)."""

from __future__ import annotations

from COAT_runtime_protocol import ConcernRelationType

RELATION_TYPES: tuple[ConcernRelationType, ...] = tuple(ConcernRelationType)

__all__ = ["RELATION_TYPES", "ConcernRelationType"]
