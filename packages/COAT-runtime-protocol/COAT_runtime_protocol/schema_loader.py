"""Helpers for locating and loading the bundled JSON Schemas."""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

SCHEMA_FILES: tuple[str, ...] = (
    "concern.schema.json",
    "meta_concern.schema.json",
    "joinpoint.schema.json",
    "pointcut.schema.json",
    "advice.schema.json",
    "weaving.schema.json",
    "copr.schema.json",
    "concern_vector.schema.json",
    "concern_injection.schema.json",
)


def schema_dir() -> Path:
    """Return the directory containing the bundled JSON Schemas."""
    return Path(__file__).resolve().parent / "schemas"


@cache
def load_schema(name: str) -> dict[str, Any]:
    """Load a single schema by filename (e.g. ``concern.schema.json``)."""
    if name not in SCHEMA_FILES:
        raise KeyError(f"Unknown schema: {name!r}. Known: {SCHEMA_FILES}")
    path = schema_dir() / name
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def schemas() -> dict[str, dict[str, Any]]:
    """Load every bundled schema, keyed by filename."""
    return {name: load_schema(name) for name in SCHEMA_FILES}
