"""Stable metric names emitted by the core (v0.2 §8)."""

from __future__ import annotations

METRIC_NAMES: tuple[str, ...] = (
    "opencoat_concerns_active",
    "opencoat_concerns_extracted_total",
    "opencoat_injection_tokens",
    "opencoat_pointcut_match_latency_ms",
    "opencoat_advice_latency_ms",
    "opencoat_verification_satisfied_ratio",
    "opencoat_dcn_nodes",
    "opencoat_dcn_edges",
)
