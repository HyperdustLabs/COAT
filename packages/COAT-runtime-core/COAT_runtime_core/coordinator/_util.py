"""Internal helpers shared across the coordinator pipeline.

Kept private to the package (leading underscore) because the only callers
are sibling modules; consumers outside the coordinator should not depend
on these helpers directly.
"""

from __future__ import annotations


def clamp01(value: float) -> float:
    """Clamp *value* into the closed unit interval ``[0, 1]``.

    Used wherever the pipeline mixes externally-supplied floats (matcher
    scores, context-derived signals) with envelope fields that the
    pydantic models already constrain to ``[0, 1]``. Centralising the
    clamp keeps the bounds rule in one place.
    """
    if value <= 0.0:
        return 0.0
    if value >= 1.0:
        return 1.0
    return float(value)


__all__ = ["clamp01"]
