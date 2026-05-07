"""M0 smoke tests — every backend skeleton imports."""

from __future__ import annotations

import importlib

import pytest


@pytest.mark.parametrize(
    "modname",
    [
        "COAT_runtime_storage",
        "COAT_runtime_storage.memory",
        "COAT_runtime_storage.memory.concern_store",
        "COAT_runtime_storage.memory.dcn_store",
        "COAT_runtime_storage.sqlite",
        "COAT_runtime_storage.jsonl",
        "COAT_runtime_storage.postgres",
        "COAT_runtime_storage.vector",
    ],
)
def test_module_imports(modname: str) -> None:
    importlib.import_module(modname)


def test_memory_backends_implement_protocols() -> None:
    """Even though methods raise NotImplementedError, the protocol shape must match."""
    from COAT_runtime_core.ports import ConcernStore, DCNStore
    from COAT_runtime_storage.memory import MemoryConcernStore, MemoryDCNStore

    assert isinstance(MemoryConcernStore(), ConcernStore)
    assert isinstance(MemoryDCNStore(), DCNStore)


def test_sqlite_schema_present() -> None:
    from importlib.resources import files

    schema = files("COAT_runtime_storage.sqlite").joinpath("schema.sql").read_text()
    assert "CREATE TABLE IF NOT EXISTS concerns" in schema
    assert "CREATE TABLE IF NOT EXISTS concern_relations" in schema
