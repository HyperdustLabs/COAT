"""M0 smoke tests — every backend skeleton imports."""

from __future__ import annotations

import importlib

import pytest


@pytest.mark.parametrize(
    "modname",
    [
        "opencoat_runtime_storage",
        "opencoat_runtime_storage.memory",
        "opencoat_runtime_storage.memory.concern_store",
        "opencoat_runtime_storage.memory.dcn_store",
        "opencoat_runtime_storage.sqlite",
        "opencoat_runtime_storage.jsonl",
        "opencoat_runtime_storage.postgres",
        "opencoat_runtime_storage.vector",
    ],
)
def test_module_imports(modname: str) -> None:
    importlib.import_module(modname)


def test_memory_backends_implement_protocols() -> None:
    """Even though methods raise NotImplementedError, the protocol shape must match."""
    from opencoat_runtime_core.ports import ConcernStore, DCNStore
    from opencoat_runtime_storage.memory import MemoryConcernStore, MemoryDCNStore

    assert isinstance(MemoryConcernStore(), ConcernStore)
    assert isinstance(MemoryDCNStore(), DCNStore)


def test_sqlite_schema_present() -> None:
    from importlib.resources import files

    schema = files("opencoat_runtime_storage.sqlite").joinpath("schema.sql").read_text()
    assert "CREATE TABLE IF NOT EXISTS concerns" in schema
    assert "CREATE TABLE IF NOT EXISTS concern_relations" in schema
