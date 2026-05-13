"""Behavioural tests for :class:`MemoryDCNStore`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from opencoat_runtime_core.ports import DCNStore
from opencoat_runtime_protocol import Concern, ConcernRelationType, LifecycleState
from opencoat_runtime_storage.memory import MemoryDCNStore


def _concern(cid: str, *, name: str | None = None) -> Concern:
    return Concern(id=cid, name=name or cid)


def _ts(offset_seconds: int = 0) -> datetime:
    return datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=offset_seconds)


# ---------------------------------------------------------------------------
# Protocol shape
# ---------------------------------------------------------------------------


def test_implements_protocol() -> None:
    assert isinstance(MemoryDCNStore(), DCNStore)


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


def test_add_node_stores_independent_copy() -> None:
    store = MemoryDCNStore()
    original = _concern("c1", name="alpha")
    store.add_node(original)

    original.name = "tampered"
    fetched = store.get_node("c1")
    assert fetched is not None
    assert fetched.name == "alpha"


def test_add_node_rejects_empty_id() -> None:
    with pytest.raises(ValueError):
        MemoryDCNStore().add_node(Concern(id="", name="x"))


def test_remove_node_cascades_to_edges_and_activations() -> None:
    store = MemoryDCNStore()
    store.add_node(_concern("a"))
    store.add_node(_concern("b"))
    store.add_edge("a", "b", ConcernRelationType.ACTIVATES)
    store.log_activation("a", "jp1", 0.7, _ts())

    store.remove_node("a")
    assert "a" not in store
    assert store.edge_count() == 0
    assert list(store.activation_log()) == []


def test_remove_node_idempotent() -> None:
    store = MemoryDCNStore()
    store.remove_node("missing")  # should not raise


# ---------------------------------------------------------------------------
# Edges
# ---------------------------------------------------------------------------


def test_add_edge_requires_both_nodes() -> None:
    store = MemoryDCNStore()
    store.add_node(_concern("a"))
    with pytest.raises(KeyError):
        store.add_edge("a", "b", ConcernRelationType.ACTIVATES)
    with pytest.raises(KeyError):
        store.add_edge("c", "a", ConcernRelationType.ACTIVATES)


def test_add_edge_validates_weight() -> None:
    store = MemoryDCNStore()
    store.add_node(_concern("a"))
    store.add_node(_concern("b"))
    with pytest.raises(ValueError):
        store.add_edge("a", "b", ConcernRelationType.ACTIVATES, weight=1.5)
    with pytest.raises(ValueError):
        store.add_edge("a", "b", ConcernRelationType.ACTIVATES, weight=-0.1)


def test_multiple_relations_between_same_pair_coexist() -> None:
    store = MemoryDCNStore()
    store.add_node(_concern("a"))
    store.add_node(_concern("b"))
    store.add_edge("a", "b", ConcernRelationType.ACTIVATES, weight=0.8)
    store.add_edge("a", "b", ConcernRelationType.CONSTRAINS, weight=0.4)

    assert store.edge_count() == 2
    assert store.edge_weight("a", "b", ConcernRelationType.ACTIVATES) == 0.8
    assert store.edge_weight("a", "b", ConcernRelationType.CONSTRAINS) == 0.4


def test_remove_edge_only_drops_the_specified_relation() -> None:
    store = MemoryDCNStore()
    store.add_node(_concern("a"))
    store.add_node(_concern("b"))
    store.add_edge("a", "b", ConcernRelationType.ACTIVATES)
    store.add_edge("a", "b", ConcernRelationType.CONSTRAINS)

    store.remove_edge("a", "b", ConcernRelationType.ACTIVATES)

    assert store.edge_weight("a", "b", ConcernRelationType.ACTIVATES) is None
    assert store.edge_weight("a", "b", ConcernRelationType.CONSTRAINS) == 1.0


def test_remove_edge_idempotent() -> None:
    MemoryDCNStore().remove_edge("a", "b", ConcernRelationType.ACTIVATES)


# ---------------------------------------------------------------------------
# Neighbors
# ---------------------------------------------------------------------------


def test_neighbors_returns_unique_outgoing_in_insertion_order() -> None:
    store = MemoryDCNStore()
    for cid in "abcd":
        store.add_node(_concern(cid))
    store.add_edge("a", "b", ConcernRelationType.ACTIVATES)
    store.add_edge("a", "c", ConcernRelationType.SUPPRESSES)
    store.add_edge("a", "b", ConcernRelationType.CONSTRAINS)
    store.add_edge("a", "d", ConcernRelationType.ACTIVATES)

    assert store.neighbors("a") == ["b", "c", "d"]


def test_neighbors_filtered_by_relation() -> None:
    store = MemoryDCNStore()
    for cid in "abcd":
        store.add_node(_concern(cid))
    store.add_edge("a", "b", ConcernRelationType.ACTIVATES)
    store.add_edge("a", "c", ConcernRelationType.SUPPRESSES)
    store.add_edge("a", "d", ConcernRelationType.ACTIVATES)

    assert store.neighbors("a", relation_type=ConcernRelationType.ACTIVATES) == ["b", "d"]
    assert store.neighbors("a", relation_type=ConcernRelationType.VERIFIES) == []


# ---------------------------------------------------------------------------
# Activation history
# ---------------------------------------------------------------------------


def test_log_activation_requires_existing_node() -> None:
    store = MemoryDCNStore()
    with pytest.raises(KeyError):
        store.log_activation("ghost", "jp1", 0.5, _ts())


def test_log_activation_validates_score() -> None:
    store = MemoryDCNStore()
    store.add_node(_concern("a"))
    with pytest.raises(ValueError):
        store.log_activation("a", "jp1", 1.1, _ts())


def test_activation_log_filters_and_limits() -> None:
    store = MemoryDCNStore()
    store.add_node(_concern("a"))
    store.add_node(_concern("b"))
    for i in range(5):
        store.log_activation("a", f"jp{i}", 0.1 * i, _ts(i))
    store.log_activation("b", "jpb", 0.9, _ts(100))

    all_records = list(store.activation_log())
    assert len(all_records) == 6

    only_a = list(store.activation_log("a"))
    assert {r["concern_id"] for r in only_a} == {"a"}
    assert len(only_a) == 5

    last_two_a = list(store.activation_log("a", limit=2))
    assert [r["joinpoint_id"] for r in last_two_a] == ["jp3", "jp4"]


def test_activation_log_zero_limit_returns_empty() -> None:
    store = MemoryDCNStore()
    store.add_node(_concern("a"))
    for i in range(3):
        store.log_activation("a", f"jp{i}", 0.1, _ts(i))

    assert list(store.activation_log(limit=0)) == []
    assert list(store.activation_log("a", limit=0)) == []


def test_activation_log_negative_limit_returns_empty() -> None:
    store = MemoryDCNStore()
    store.add_node(_concern("a"))
    store.log_activation("a", "jp", 0.5, _ts())

    assert list(store.activation_log(limit=-1)) == []
    assert list(store.activation_log("a", limit=-5)) == []


def test_activation_log_returns_independent_records() -> None:
    store = MemoryDCNStore()
    store.add_node(_concern("a"))
    store.log_activation("a", "jp1", 0.5, _ts())

    records = list(store.activation_log())
    records[0]["score"] = 999
    assert next(iter(store.activation_log()))["score"] == 0.5


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------


def test_merge_rewires_edges_and_activations() -> None:
    store = MemoryDCNStore()
    for cid in "sdxy":
        store.add_node(_concern(cid))
    store.add_edge("s", "x", ConcernRelationType.ACTIVATES, weight=0.5)
    store.add_edge("y", "s", ConcernRelationType.CONSTRAINS, weight=0.7)
    store.add_edge("d", "x", ConcernRelationType.ACTIVATES, weight=0.3)
    store.log_activation("s", "jp1", 0.6, _ts())

    store.merge("s", "d")

    assert "s" not in store
    assert store.edge_weight("d", "x", ConcernRelationType.ACTIVATES) == 0.5
    assert store.edge_weight("y", "d", ConcernRelationType.CONSTRAINS) == 0.7
    assert {r["concern_id"] for r in store.activation_log()} == {"d"}


def test_merge_drops_self_loops_created_by_rewire() -> None:
    store = MemoryDCNStore()
    store.add_node(_concern("s"))
    store.add_node(_concern("d"))
    store.add_edge("s", "d", ConcernRelationType.ACTIVATES)

    store.merge("s", "d")

    assert store.edge_count() == 0


def test_merge_same_id_is_noop() -> None:
    store = MemoryDCNStore()
    store.add_node(_concern("a"))
    store.merge("a", "a")
    assert "a" in store


def test_merge_unknown_node_raises() -> None:
    store = MemoryDCNStore()
    store.add_node(_concern("a"))
    with pytest.raises(KeyError):
        store.merge("a", "missing")
    with pytest.raises(KeyError):
        store.merge("missing", "a")


# ---------------------------------------------------------------------------
# Archive
# ---------------------------------------------------------------------------


def test_archive_marks_lifecycle_state() -> None:
    store = MemoryDCNStore()
    store.add_node(_concern("a"))
    store.archive("a")

    fetched = store.get_node("a")
    assert fetched is not None
    assert fetched.lifecycle_state == LifecycleState.ARCHIVED.value


def test_archive_unknown_is_noop() -> None:
    MemoryDCNStore().archive("ghost")
