"""Stable metric names emitted by the core (v0.2 §8)."""

from __future__ import annotations

METRIC_NAMES: tuple[str, ...] = (
    "COATr_concerns_active",
    "COATr_concerns_extracted_total",
    "COATr_injection_tokens",
    "COATr_pointcut_match_latency_ms",
    "COATr_advice_latency_ms",
    "COATr_verification_satisfied_ratio",
    "COATr_dcn_nodes",
    "COATr_dcn_edges",
)
