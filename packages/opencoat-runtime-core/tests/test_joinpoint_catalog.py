"""Tests for the joinpoint catalog."""

from __future__ import annotations

from opencoat_runtime_core.joinpoint import JOINPOINT_CATALOG, JoinpointCatalog, JoinpointLevel
from opencoat_runtime_core.joinpoint.catalog import CatalogEntry


def test_default_catalog_covers_v01_section_12() -> None:
    assert "runtime_start" in JOINPOINT_CATALOG
    assert "before_response" in JOINPOINT_CATALOG
    assert "user_message" in JOINPOINT_CATALOG
    assert "system_prompt.role_definition" in JOINPOINT_CATALOG


def test_catalog_lookup_returns_entry_with_level() -> None:
    entry = JOINPOINT_CATALOG.get("before_tool_call")
    assert entry is not None
    assert entry.level is JoinpointLevel.LIFECYCLE


def test_catalog_by_level() -> None:
    runtime_entries = JOINPOINT_CATALOG.by_level(JoinpointLevel.RUNTIME)
    assert {e.name for e in runtime_entries} >= {
        "runtime_start",
        "runtime_stop",
        "runtime_tick",
    }
    lifecycle_entries = JOINPOINT_CATALOG.by_level(JoinpointLevel.LIFECYCLE)
    assert any(e.name == "on_user_input" for e in lifecycle_entries)


def test_catalog_register_extends_at_runtime() -> None:
    cat = JoinpointCatalog()
    cat.register(CatalogEntry("custom_tick", JoinpointLevel.RUNTIME, "host-defined"))
    assert "custom_tick" in cat
    assert cat.get("custom_tick").level is JoinpointLevel.RUNTIME
    assert len(cat) == 1


def test_catalog_iteration_yields_entries() -> None:
    seen = {e.name for e in JOINPOINT_CATALOG}
    assert "before_response" in seen
    assert len(JOINPOINT_CATALOG) == len(seen)


def test_levels_have_string_label() -> None:
    assert JoinpointLevel.RUNTIME.label == "runtime"
    assert JoinpointLevel.PROMPT_SECTION.label == "prompt_section"
    assert JoinpointLevel.SEMANTIC_SPAN.label == "span"
