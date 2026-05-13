"""Validate that every bundled JSON Schema is itself well-formed
(Draft 2020-12) and that all cross-file ``$ref`` references resolve.
"""

from __future__ import annotations

import json

import pytest
from jsonschema import Draft202012Validator
from opencoat_runtime_protocol import SCHEMA_FILES, load_schema, schema_dir
from opencoat_runtime_protocol.schema_loader import schemas
from referencing import Registry, Resource


def _registry() -> Registry:
    """Build a referencing registry that resolves cross-file $refs by filename."""
    registry: Registry = Registry()
    for name in SCHEMA_FILES:
        schema = load_schema(name)
        resource = Resource.from_contents(schema)
        registry = registry.with_resource(uri=name, resource=resource)
        if schema.get("$id"):
            registry = registry.with_resource(uri=schema["$id"], resource=resource)
    return registry


@pytest.mark.parametrize("name", SCHEMA_FILES)
def test_schema_file_exists_and_is_valid_json(name: str) -> None:
    path = schema_dir() / name
    assert path.exists(), f"missing schema file: {name}"
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    assert isinstance(data, dict)
    assert data.get("$schema", "").startswith("https://json-schema.org/draft/2020-12")


@pytest.mark.parametrize("name", SCHEMA_FILES)
def test_schema_is_metaschema_valid(name: str) -> None:
    schema = load_schema(name)
    Draft202012Validator.check_schema(schema)


def test_all_schemas_loadable() -> None:
    all_schemas = schemas()
    assert set(all_schemas.keys()) == set(SCHEMA_FILES)
    for name, schema in all_schemas.items():
        assert "$id" in schema, f"{name} missing $id"
        assert "title" in schema, f"{name} missing title"


def test_cross_file_refs_resolve() -> None:
    """Each schema must successfully construct a validator with the registry."""
    registry = _registry()
    for name in SCHEMA_FILES:
        schema = load_schema(name)
        validator = Draft202012Validator(schema, registry=registry)
        assert validator is not None
