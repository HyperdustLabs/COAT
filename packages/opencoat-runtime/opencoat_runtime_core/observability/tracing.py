"""Stable span names emitted by the core (v0.2 §8).

The full turn-loop emits spans in this order; each has ``concern_id`` /
``joinpoint_id`` / ``turn_id`` attributes.
"""

from __future__ import annotations

SPAN_NAMES: tuple[str, ...] = (
    "extract",
    "separate",
    "build",
    "match",
    "coordinate",
    "resolve",
    "advise",
    "weave",
    "verify",
)
