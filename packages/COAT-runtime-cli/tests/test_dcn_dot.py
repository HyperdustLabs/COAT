"""Tests for :func:`COAT_runtime_cli.visualize.dcn_dot.dcn_to_dot` (M4 PR-22)."""

from __future__ import annotations

from COAT_runtime_cli.visualize.dcn_dot import dcn_to_dot


def test_empty_snapshot_returns_valid_skeleton() -> None:
    dot = dcn_to_dot({"concerns": [], "activation_log": []})
    assert dot.startswith("digraph DCN {")
    assert dot.strip().endswith("}")


def test_concern_nodes_are_rendered() -> None:
    snap = {
        "concerns": [
            {"id": "c-1", "name": "first", "lifecycle_state": "active"},
            {"id": "c-2", "name": "second", "lifecycle_state": "weakened"},
        ],
        "activation_log": [],
    }
    dot = dcn_to_dot(snap)
    assert "c_c_1" in dot
    assert "c_c_2" in dot
    assert '"first\\n(active)"' in dot
    assert '"second\\n(weakened)"' in dot


def test_edges_count_repeated_activations() -> None:
    snap = {
        "concerns": [{"id": "c-1", "name": "one", "lifecycle_state": "active"}],
        "activation_log": [
            {"concern_id": "c-1", "joinpoint_id": "before_response"},
            {"concern_id": "c-1", "joinpoint_id": "before_response"},
            {"concern_id": "c-1", "joinpoint_id": "after_response"},
        ],
    }
    dot = dcn_to_dot(snap)
    # repeated edge gets a count label
    assert 'j_before_response -> c_c_1 [label="2"]' in dot
    # singleton edge gets no label
    assert "j_after_response -> c_c_1;" in dot


def test_dangling_activation_creates_stub_concern_node() -> None:
    snap = {
        "concerns": [],
        "activation_log": [
            {"concern_id": "ghost", "joinpoint_id": "before_response"},
        ],
    }
    dot = dcn_to_dot(snap)
    assert "style=dashed" in dot
    assert "c_ghost" in dot
    assert "j_before_response -> c_ghost" in dot


def test_unsafe_characters_in_ids_are_sanitised() -> None:
    # IDs with dots/colons must turn into valid DOT identifiers (the
    # label can still contain them, only the node id needs cleaning).
    snap = {
        "concerns": [{"id": "ns:rule.1", "name": "weird", "lifecycle_state": "active"}],
        "activation_log": [],
    }
    dot = dcn_to_dot(snap)
    assert "c_ns_rule_1" in dot
    assert '"weird\\n(active)"' in dot


def test_rows_missing_required_fields_are_skipped() -> None:
    snap = {
        "concerns": [{"id": "", "name": "no id"}],
        "activation_log": [
            {"concern_id": "c-1"},  # missing joinpoint_id
            {"joinpoint_id": "before_response"},  # missing concern_id
        ],
    }
    dot = dcn_to_dot(snap)
    # No edges, no nodes (other than the boilerplate).
    assert " -> " not in dot
    assert "shape=box" not in dot
