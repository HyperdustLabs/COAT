"""Tests for :func:`opencoat_runtime_cli.visualize.dcn_dot.dcn_to_dot` (M4 PR-22)."""

from __future__ import annotations

from opencoat_runtime_cli.visualize.dcn_dot import dcn_to_dot


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
    assert '"c:c-1"' in dot
    assert '"c:c-2"' in dot
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
    assert '"j:before_response" -> "c:c-1" [label="2"]' in dot
    assert '"j:after_response" -> "c:c-1";' in dot


def test_dangling_activation_creates_stub_concern_node() -> None:
    snap = {
        "concerns": [],
        "activation_log": [
            {"concern_id": "ghost", "joinpoint_id": "before_response"},
        ],
    }
    dot = dcn_to_dot(snap)
    assert "style=dashed" in dot
    assert '"c:ghost"' in dot
    assert '"j:before_response" -> "c:ghost"' in dot


def test_unsafe_characters_in_ids_are_quoted_not_collapsed() -> None:
    # IDs with dots / colons / dashes appear verbatim inside the
    # quoted DOT id; the label is independent and can still contain
    # them too.
    snap = {
        "concerns": [{"id": "ns:rule.1", "name": "weird", "lifecycle_state": "active"}],
        "activation_log": [],
    }
    dot = dcn_to_dot(snap)
    assert '"c:ns:rule.1"' in dot
    assert '"weird\\n(active)"' in dot


def test_node_ids_distinguish_dash_vs_underscore() -> None:
    """Codex P2 on PR-22 (#26): two ids that the old sanitiser
    collapsed to ``a_b`` must end up as *different* DOT nodes.
    """
    snap = {
        "concerns": [
            {"id": "a-b", "name": "dashy", "lifecycle_state": "active"},
            {"id": "a_b", "name": "scorey", "lifecycle_state": "active"},
        ],
        "activation_log": [
            {"concern_id": "a-b", "joinpoint_id": "before_response"},
            {"concern_id": "a_b", "joinpoint_id": "before_response"},
        ],
    }
    dot = dcn_to_dot(snap)
    # both source ids survive verbatim and appear as distinct nodes
    assert '"c:a-b"' in dot
    assert '"c:a_b"' in dot
    # both labels are emitted, proving no merge happened
    assert "dashy" in dot
    assert "scorey" in dot
    # two box nodes for the two concerns
    assert dot.count("[shape=box,") == 2
    # two distinct edges from the same joinpoint
    assert '"j:before_response" -> "c:a-b"' in dot
    assert '"j:before_response" -> "c:a_b"' in dot


def test_quote_escapes_embedded_quote_in_id() -> None:
    """An id containing ``"`` must not break the surrounding DOT
    quotes — the embedded quote should be escaped as ``\\"`` so the
    line stays parseable.
    """
    snap = {
        "concerns": [
            {"id": 'weird"id', "name": "n", "lifecycle_state": "active"},
        ],
        "activation_log": [],
    }
    dot = dcn_to_dot(snap)
    assert '"c:weird\\"id"' in dot


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
