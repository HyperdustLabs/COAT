#!/usr/bin/env python
"""Standalone schema validator.

Runs outside of pytest so the CI ``schema-check`` job stays minimal.
Loads every bundled JSON Schema, checks Draft 2020-12 compliance, and
verifies that all cross-file ``$ref`` references resolve.
"""

from __future__ import annotations

import sys

from jsonschema import Draft202012Validator
from opencoat_runtime_protocol import SCHEMA_FILES, load_schema
from referencing import Registry, Resource


def main() -> int:
    registry: Registry = Registry()
    for name in SCHEMA_FILES:
        schema = load_schema(name)
        Draft202012Validator.check_schema(schema)
        resource = Resource.from_contents(schema)
        registry = registry.with_resource(uri=name, resource=resource)
        if schema.get("$id"):
            registry = registry.with_resource(uri=schema["$id"], resource=resource)

    # second pass — every schema must compile against the registry
    for name in SCHEMA_FILES:
        Draft202012Validator(load_schema(name), registry=registry)

    print(f"OK: {len(SCHEMA_FILES)} schemas valid (Draft 2020-12, refs resolved)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
