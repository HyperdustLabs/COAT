"""Pure-function query helpers shared by in-memory backends.

Kept separate so the same predicates can be reused by sqlite/jsonl tests
and by any future debug tools without dragging in the storage classes.
"""

from __future__ import annotations

from typing import TypedDict

from COAT_runtime_protocol import Concern


class Filter(TypedDict, total=False):
    """Optional filter parameters for :meth:`MemoryConcernStore.list`."""

    kind: str | None
    tag: str | None
    lifecycle_state: str | None


def apply_filter(concern: Concern, flt: Filter) -> bool:
    """Return ``True`` if ``concern`` matches every non-``None`` filter key."""
    if (kind := flt.get("kind")) is not None and concern.kind != kind:
        return False
    if (state := flt.get("lifecycle_state")) is not None and concern.lifecycle_state != state:
        return False
    tag = flt.get("tag")
    return not (tag is not None and tag not in concern.generated_tags)


def substring_match(concern: Concern, needle: str) -> bool:
    """Case-insensitive substring search over ``name`` and ``description``."""
    haystack = f"{concern.name}\n{concern.description}".lower()
    return needle in haystack


__all__ = ["Filter", "apply_filter", "substring_match"]
