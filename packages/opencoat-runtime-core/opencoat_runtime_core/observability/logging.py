"""Tiny logger helper — keeps the core dependency-free.

Emits standard ``logging`` records with a stable prefix so log shippers
can isolate runtime traffic.
"""

from __future__ import annotations

import logging

_LOG_PREFIX = "opencoat"


def get_logger(name: str) -> logging.Logger:
    """Return a logger named ``opencoat.<name>``."""
    return logging.getLogger(f"{_LOG_PREFIX}.{name}")
