"""Behavioural tests for :class:`SqliteDCNStore` (M3 PR-14).

The SQLite DCN backend must behave identically to the in-memory one
for every public-API call — same protocol, same node / edge /
activation semantics, same ``merge`` behaviour. The first half of
this file ports ``test_memory_dcn_store.py`` with
``MemoryDCNStore`` swapped for ``SqliteDCNStore``; the second half
pins SQLite-specific behaviour (file persistence, FK cascade
correctness, transaction rollback, schema bootstrap, threading)
that the memory backend can't exhibit.

All tests run against ``:memory:`` databases unless they explicitly
need to test on-disk persistence — keeps the suite hermetic.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from opencoat_runtime_core.ports import DCNStore
from opencoat_runtime_protocol import Concern, ConcernRelationType, LifecycleState
from opencoat_runtime_storage.memory import MemoryDCNStore
from opencoat_runtime_storage.sqlite import (
    DCN_SCHEMA_VERSION,
    SqliteDCNStore,
    bootstrap_dcn_sql,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _concern(cid: str, *, name: str | None = None) -> Concern:
    return Concern(id=cid, name=name or cid)


def _ts(offset_seconds: int = 0) -> datetime:
    return datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=offset_seconds)


@pytest.fixture
def store() -> SqliteDCNStore:
    """Per-test ``:memory:`` store. Closed by GC."""
    return SqliteDCNStore(":memory:")


# ---------------------------------------------------------------------------
# Protocol shape
# ---------------------------------------------------------------------------


class TestProtocol:
    def test_implements_dcn_store_protocol(self, store: SqliteDCNStore) -> None:
        assert isinstance(store, DCNStore)

    def test_default_path_is_in_memory(self) -> None:
        assert SqliteDCNStore().path == ":memory:"

    def test_path_argument_is_preserved(self, tmp_path: Path) -> None:
        db = tmp_path / "dcn.db"
        s = SqliteDCNStore(db)
        try:
            assert s.path == str(db)
        finally:
            s.close()


# ---------------------------------------------------------------------------
# Nodes (port of MemoryDCNStore tests)
# ---------------------------------------------------------------------------


class TestNodes:
    def test_add_node_stores_independent_copy(self, store: SqliteDCNStore) -> None:
        original = _concern("c1", name="alpha")
        store.add_node(original)

        # Mutating the original after add_node must not leak into the
        # store; sqlite gets this for free via the JSON dump, but we
        # pin it so a future "store the model directly" optimisation
        # can't break the contract.
        original.name = "tampered"
        fetched = store.get_node("c1")
        assert fetched is not None
        assert fetched.name == "alpha"

    def test_add_node_rejects_empty_id(self, store: SqliteDCNStore) -> None:
        with pytest.raises(ValueError, match="id"):
            store.add_node(Concern(id="", name="x"))

    def test_add_node_overwrites_existing(self, store: SqliteDCNStore) -> None:
        store.add_node(_concern("a", name="v1"))
        store.add_node(_concern("a", name="v2"))
        fetched = store.get_node("a")
        assert fetched is not None
        assert fetched.name == "v2"
        assert len(store) == 1

    def test_remove_node_cascades_to_edges_and_activations(self, store: SqliteDCNStore) -> None:
        store.add_node(_concern("a"))
        store.add_node(_concern("b"))
        store.add_edge("a", "b", ConcernRelationType.ACTIVATES)
        store.log_activation("a", "jp1", 0.7, _ts())

        store.remove_node("a")
        assert "a" not in store
        # FK CASCADE on both edge endpoints + activation.concern_id.
        assert store.edge_count() == 0
        assert list(store.activation_log()) == []

    def test_remove_node_idempotent(self, store: SqliteDCNStore) -> None:
        store.remove_node("missing")  # should not raise

    def test_remove_node_cascades_when_node_is_only_edge_dst(self, store: SqliteDCNStore) -> None:
        # Sqlite FKs reference both src AND dst, so removing the dst
        # of an edge should also clean up the edge. Memory backend
        # does this in its remove_node loop; pin parity.
        store.add_node(_concern("a"))
        store.add_node(_concern("b"))
        store.add_edge("a", "b", ConcernRelationType.ACTIVATES)
        store.remove_node("b")
        assert store.edge_count() == 0


# ---------------------------------------------------------------------------
# Edges
# ---------------------------------------------------------------------------


class TestEdges:
    def test_add_edge_requires_both_nodes(self, store: SqliteDCNStore) -> None:
        # Both endpoints are checked; the missing one shows up in the
        # KeyError message (src takes priority — same as the memory
        # backend's check order).
        store.add_node(_concern("a"))
        with pytest.raises(KeyError, match="dst"):
            store.add_edge("a", "b", ConcernRelationType.ACTIVATES)
        with pytest.raises(KeyError, match="src"):
            store.add_edge("c", "a", ConcernRelationType.ACTIVATES)

    @pytest.mark.parametrize("bad_weight", [-0.1, 1.1, 2.0, -1.0])
    def test_add_edge_validates_weight(self, store: SqliteDCNStore, bad_weight: float) -> None:
        store.add_node(_concern("a"))
        store.add_node(_concern("b"))
        with pytest.raises(ValueError, match="weight"):
            store.add_edge("a", "b", ConcernRelationType.ACTIVATES, weight=bad_weight)

    def test_add_edge_accepts_boundary_weights(self, store: SqliteDCNStore) -> None:
        # 0.0 and 1.0 are valid (inclusive bounds).
        store.add_node(_concern("a"))
        store.add_node(_concern("b"))
        store.add_edge("a", "b", ConcernRelationType.ACTIVATES, weight=0.0)
        store.add_edge("a", "b", ConcernRelationType.CONSTRAINS, weight=1.0)
        assert store.edge_count() == 2

    def test_multiple_relations_between_same_pair_coexist(self, store: SqliteDCNStore) -> None:
        store.add_node(_concern("a"))
        store.add_node(_concern("b"))
        store.add_edge("a", "b", ConcernRelationType.ACTIVATES, weight=0.8)
        store.add_edge("a", "b", ConcernRelationType.CONSTRAINS, weight=0.4)

        assert store.edge_count() == 2
        assert store.edge_weight("a", "b", ConcernRelationType.ACTIVATES) == 0.8
        assert store.edge_weight("a", "b", ConcernRelationType.CONSTRAINS) == 0.4

    def test_remove_edge_only_drops_the_specified_relation(self, store: SqliteDCNStore) -> None:
        store.add_node(_concern("a"))
        store.add_node(_concern("b"))
        store.add_edge("a", "b", ConcernRelationType.ACTIVATES)
        store.add_edge("a", "b", ConcernRelationType.CONSTRAINS)

        store.remove_edge("a", "b", ConcernRelationType.ACTIVATES)

        assert store.edge_weight("a", "b", ConcernRelationType.ACTIVATES) is None
        assert store.edge_weight("a", "b", ConcernRelationType.CONSTRAINS) == 1.0

    def test_remove_edge_idempotent(self, store: SqliteDCNStore) -> None:
        store.remove_edge("a", "b", ConcernRelationType.ACTIVATES)  # no nodes, no rows

    def test_add_edge_twice_updates_weight_without_reordering(self, store: SqliteDCNStore) -> None:
        # The memory backend's ``self._edges[key] = weight`` updates
        # in place — the dict-iteration position doesn't move. We
        # mirror that by preserving ``seq`` on UPSERT.
        for cid in "abc":
            store.add_node(_concern(cid))
        store.add_edge("a", "b", ConcernRelationType.ACTIVATES, weight=0.3)
        store.add_edge("a", "c", ConcernRelationType.ACTIVATES, weight=0.5)
        store.add_edge("a", "b", ConcernRelationType.ACTIVATES, weight=0.9)  # update

        assert store.edge_weight("a", "b", ConcernRelationType.ACTIVATES) == 0.9
        # neighbors order unchanged: b first (was inserted first),
        # then c — even though we touched b last.
        assert store.neighbors("a") == ["b", "c"]


# ---------------------------------------------------------------------------
# Neighbors
# ---------------------------------------------------------------------------


class TestNeighbors:
    def test_neighbors_returns_unique_outgoing_in_insertion_order(
        self, store: SqliteDCNStore
    ) -> None:
        for cid in "abcd":
            store.add_node(_concern(cid))
        store.add_edge("a", "b", ConcernRelationType.ACTIVATES)
        store.add_edge("a", "c", ConcernRelationType.SUPPRESSES)
        store.add_edge("a", "b", ConcernRelationType.CONSTRAINS)
        store.add_edge("a", "d", ConcernRelationType.ACTIVATES)

        # Memory backend yields each dst once, in the order of its
        # FIRST appearance — sqlite mirrors this with MIN(seq) per dst.
        assert store.neighbors("a") == ["b", "c", "d"]

    def test_neighbors_filtered_by_relation(self, store: SqliteDCNStore) -> None:
        for cid in "abcd":
            store.add_node(_concern(cid))
        store.add_edge("a", "b", ConcernRelationType.ACTIVATES)
        store.add_edge("a", "c", ConcernRelationType.SUPPRESSES)
        store.add_edge("a", "d", ConcernRelationType.ACTIVATES)

        assert store.neighbors("a", relation_type=ConcernRelationType.ACTIVATES) == ["b", "d"]
        assert store.neighbors("a", relation_type=ConcernRelationType.VERIFIES) == []

    def test_neighbors_empty_for_unknown_concern(self, store: SqliteDCNStore) -> None:
        assert store.neighbors("never-added") == []


# ---------------------------------------------------------------------------
# Activation history
# ---------------------------------------------------------------------------


class TestActivations:
    def test_log_activation_requires_existing_node(self, store: SqliteDCNStore) -> None:
        with pytest.raises(KeyError, match="ghost"):
            store.log_activation("ghost", "jp1", 0.5, _ts())

    @pytest.mark.parametrize("bad_score", [-0.01, 1.01, 1.5, -2.0])
    def test_log_activation_validates_score(self, store: SqliteDCNStore, bad_score: float) -> None:
        store.add_node(_concern("a"))
        with pytest.raises(ValueError, match="score"):
            store.log_activation("a", "jp1", bad_score, _ts())

    def test_activation_log_filters_and_limits(self, store: SqliteDCNStore) -> None:
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

        # ``limit=2`` returns the LAST 2 records in chronological
        # order — the memory backend's ``snapshot[-limit:]`` semantics.
        last_two_a = list(store.activation_log("a", limit=2))
        assert [r["joinpoint_id"] for r in last_two_a] == ["jp3", "jp4"]

    @pytest.mark.parametrize("bad_limit", [0, -1, -5])
    def test_activation_log_non_positive_limit_returns_empty(
        self, store: SqliteDCNStore, bad_limit: int
    ) -> None:
        store.add_node(_concern("a"))
        for i in range(3):
            store.log_activation("a", f"jp{i}", 0.1, _ts(i))
        assert list(store.activation_log(limit=bad_limit)) == []
        assert list(store.activation_log("a", limit=bad_limit)) == []

    def test_activation_log_returns_independent_records(self, store: SqliteDCNStore) -> None:
        # Tampering the returned dict must not corrupt subsequent reads.
        store.add_node(_concern("a"))
        store.log_activation("a", "jp1", 0.5, _ts())

        records = list(store.activation_log())
        records[0]["score"] = 999
        assert next(iter(store.activation_log()))["score"] == 0.5

    def test_activation_log_preserves_datetime_type(self, store: SqliteDCNStore) -> None:
        # The memory backend stores raw datetimes; we round-trip
        # through ISO strings, so pin that the read side gives back
        # tz-aware datetimes (not raw strings).
        store.add_node(_concern("a"))
        ts = _ts(42)
        store.log_activation("a", "jp", 0.5, ts)
        rec = next(iter(store.activation_log()))
        assert isinstance(rec["ts"], datetime)
        assert rec["ts"] == ts


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------


class TestMerge:
    def test_merge_rewires_edges_and_activations(self, store: SqliteDCNStore) -> None:
        for cid in "sdxy":
            store.add_node(_concern(cid))
        store.add_edge("s", "x", ConcernRelationType.ACTIVATES, weight=0.5)
        store.add_edge("y", "s", ConcernRelationType.CONSTRAINS, weight=0.7)
        store.add_edge("d", "x", ConcernRelationType.ACTIVATES, weight=0.3)
        store.log_activation("s", "jp1", 0.6, _ts())

        store.merge("s", "d")

        assert "s" not in store
        # Collision on (d, x, activates) — ``max(0.5, 0.3)`` = 0.5.
        assert store.edge_weight("d", "x", ConcernRelationType.ACTIVATES) == 0.5
        # Pure rewire, no collision.
        assert store.edge_weight("y", "d", ConcernRelationType.CONSTRAINS) == 0.7
        # Activation reattributed.
        assert {r["concern_id"] for r in store.activation_log()} == {"d"}

    def test_merge_drops_self_loops_created_by_rewire(self, store: SqliteDCNStore) -> None:
        store.add_node(_concern("s"))
        store.add_node(_concern("d"))
        store.add_edge("s", "d", ConcernRelationType.ACTIVATES)

        store.merge("s", "d")

        assert store.edge_count() == 0

    def test_merge_same_id_is_noop(self, store: SqliteDCNStore) -> None:
        store.add_node(_concern("a"))
        store.merge("a", "a")
        assert "a" in store

    def test_merge_unknown_node_raises(self, store: SqliteDCNStore) -> None:
        store.add_node(_concern("a"))
        with pytest.raises(KeyError, match="missing"):
            store.merge("a", "missing")
        with pytest.raises(KeyError, match="missing"):
            store.merge("missing", "a")

    def test_merge_collision_keeps_first_occurrence_seq(self, store: SqliteDCNStore) -> None:
        # Pin first-occurrence-wins for seq on collision, which keeps
        # neighbors() ordering stable across merges. Memory backend
        # gets this for free via dict-iteration; sqlite has to
        # explicitly track min(seq).
        for cid in "sdxy":
            store.add_node(_concern(cid))
        # Edge that will become (d, y, ACTIVATES) after merge,
        # appears FIRST in the iteration (so its seq wins).
        store.add_edge("d", "y", ConcernRelationType.ACTIVATES, weight=0.2)
        # Edge that will collide with above: (s, y, ACTIVATES) →
        # rewired to (d, y, ACTIVATES). max(0.2, 0.9) = 0.9, but the
        # seq stays at the earlier edge's value, so neighbors order
        # is unchanged.
        store.add_edge("s", "y", ConcernRelationType.ACTIVATES, weight=0.9)
        store.add_edge("d", "x", ConcernRelationType.ACTIVATES, weight=0.5)

        store.merge("s", "d")

        # Collision: max weight wins.
        assert store.edge_weight("d", "y", ConcernRelationType.ACTIVATES) == 0.9
        # Neighbors order: y first (its seq pre-dates x), then x.
        assert store.neighbors("d") == ["y", "x"]


# ---------------------------------------------------------------------------
# Archive
# ---------------------------------------------------------------------------


class TestArchive:
    def test_archive_marks_lifecycle_state(self, store: SqliteDCNStore) -> None:
        store.add_node(_concern("a"))
        store.archive("a")

        fetched = store.get_node("a")
        assert fetched is not None
        assert fetched.lifecycle_state == LifecycleState.ARCHIVED.value

    def test_archive_unknown_is_noop(self, store: SqliteDCNStore) -> None:
        store.archive("ghost")  # must not raise

    def test_archive_updates_projected_column(self, store: SqliteDCNStore) -> None:
        # Both the body_json AND the projected lifecycle_state column
        # must reflect the archive — otherwise a future query that
        # reads the column directly (e.g. "all archived nodes") would
        # silently disagree with get_node().
        store.add_node(_concern("a"))
        store.archive("a")
        with store._lock:
            row = store._conn.execute(
                "SELECT lifecycle_state FROM dcn_nodes WHERE id = 'a';"
            ).fetchone()
        assert row["lifecycle_state"] == LifecycleState.ARCHIVED.value


# ---------------------------------------------------------------------------
# Convenience
# ---------------------------------------------------------------------------


class TestConvenience:
    def test_contains_and_len(self, store: SqliteDCNStore) -> None:
        assert "a" not in store
        store.add_node(_concern("a"))
        assert "a" in store
        assert 123 not in store  # type: ignore[operator]
        assert len(store) == 1
        store.remove_node("a")
        assert len(store) == 0


# ---------------------------------------------------------------------------
# SQLite-specific: persistence, FK cascade, schema, transactions, threading
# ---------------------------------------------------------------------------


class TestPersistence:
    def test_full_graph_survives_close_and_reopen(self, tmp_path: Path) -> None:
        # Round-trip: nodes, edges (multi-relation), activation log.
        # The whole point of this backend.
        db = tmp_path / "dcn.db"
        s1 = SqliteDCNStore(db)
        s1.add_node(_concern("a", name="alpha"))
        s1.add_node(_concern("b", name="beta"))
        s1.add_edge("a", "b", ConcernRelationType.ACTIVATES, weight=0.7)
        s1.add_edge("a", "b", ConcernRelationType.CONSTRAINS, weight=0.3)
        s1.log_activation("a", "jp1", 0.8, _ts(1))
        s1.log_activation("a", "jp2", 0.9, _ts(2))
        s1.close()

        s2 = SqliteDCNStore(db)
        try:
            assert "a" in s2
            assert "b" in s2
            assert s2.edge_weight("a", "b", ConcernRelationType.ACTIVATES) == 0.7
            assert s2.edge_weight("a", "b", ConcernRelationType.CONSTRAINS) == 0.3
            recs = list(s2.activation_log("a"))
            assert [r["joinpoint_id"] for r in recs] == ["jp1", "jp2"]
        finally:
            s2.close()

    def test_path_parent_dir_is_auto_created(self, tmp_path: Path) -> None:
        nested = tmp_path / "deep" / "nested" / "dcn.db"
        s = SqliteDCNStore(nested)
        try:
            assert nested.parent.exists()
        finally:
            s.close()

    def test_close_is_idempotent(self) -> None:
        s = SqliteDCNStore(":memory:")
        s.close()
        s.close()

    def test_context_manager_closes_on_exit(self, tmp_path: Path) -> None:
        db = tmp_path / "dcn.db"
        with SqliteDCNStore(db) as s:
            s.add_node(_concern("a"))
            assert "a" in s
        assert db.exists()


class TestSchema:
    def test_bootstrap_is_idempotent(self, tmp_path: Path) -> None:
        db = tmp_path / "dcn.db"
        with SqliteDCNStore(db) as s1:
            s1.add_node(_concern("a"))
            assert len(s1) == 1
        with SqliteDCNStore(db) as s2:
            assert len(s2) == 1

    def test_dcn_schema_version_recorded_in_meta(self, tmp_path: Path) -> None:
        db = tmp_path / "dcn.db"
        with SqliteDCNStore(db):
            with sqlite3.connect(db) as raw:
                row = raw.execute(
                    "SELECT value FROM meta WHERE key = 'dcn_schema_version';"
                ).fetchone()
            assert row is not None
            assert int(row[0]) == DCN_SCHEMA_VERSION

    def test_bootstrap_dcn_sql_creates_expected_tables(self, tmp_path: Path) -> None:
        db = tmp_path / "ad-hoc.db"
        with sqlite3.connect(db) as raw:
            raw.executescript(bootstrap_dcn_sql())
            tables = {
                row[0]
                for row in raw.execute(
                    "SELECT name FROM sqlite_master WHERE type='table';"
                ).fetchall()
            }
        assert {"dcn_nodes", "dcn_edges", "dcn_activations", "meta"} <= tables

    def test_concern_and_dcn_stores_coexist_in_one_db(self, tmp_path: Path) -> None:
        # The two stores should be safe to point at the same SQLite
        # file (both use IF NOT EXISTS, separate ``meta`` keys).
        from opencoat_runtime_storage.sqlite import SqliteConcernStore

        db = tmp_path / "shared.db"
        with SqliteConcernStore(db) as cs, SqliteDCNStore(db) as ds:
            cs.upsert(_concern("a"))
            ds.add_node(_concern("a"))
            assert len(cs) == 1
            assert len(ds) == 1


class TestForeignKeys:
    def test_foreign_keys_pragma_is_on(self, store: SqliteDCNStore) -> None:
        # Without this pragma the CASCADE clauses are silent no-ops
        # — every other test in this file would still pass and we'd
        # have a latent data-leak bug. Sentinel test.
        with store._lock:
            cur = store._conn.execute("PRAGMA foreign_keys;")
            assert cur.fetchone()[0] == 1

    def test_remove_node_cascade_drops_inbound_edges(self, store: SqliteDCNStore) -> None:
        # Sanity check that the dst-side FK cascade is wired up: a
        # node that's only an edge dst (never an src) still gets
        # its inbound edges cleaned up on remove.
        store.add_node(_concern("a"))
        store.add_node(_concern("b"))
        store.add_node(_concern("c"))
        store.add_edge("a", "c", ConcernRelationType.ACTIVATES)
        store.add_edge("b", "c", ConcernRelationType.SUPPRESSES)
        store.remove_node("c")
        assert store.edge_count() == 0

    def test_add_edge_rejects_unknown_node_with_keyerror_not_integrity(
        self, store: SqliteDCNStore
    ) -> None:
        # The FK constraint would also fire here, but as
        # IntegrityError. Our explicit pre-check raises ``KeyError``
        # to match the memory backend's exception type.
        store.add_node(_concern("a"))
        with pytest.raises(KeyError):
            store.add_edge("a", "ghost", ConcernRelationType.ACTIVATES)


class TestTransactions:
    def test_add_edge_rolls_back_on_invalid_weight_post_check(self, store: SqliteDCNStore) -> None:
        # The weight check fires BEFORE _txn() opens, so this is the
        # easy case — verify no partial state leaked.
        store.add_node(_concern("a"))
        store.add_node(_concern("b"))
        with pytest.raises(ValueError):
            store.add_edge("a", "b", ConcernRelationType.ACTIVATES, weight=2.0)
        assert store.edge_count() == 0

    def test_log_activation_unknown_node_rolls_back_inside_txn(self, store: SqliteDCNStore) -> None:
        # The KeyError fires INSIDE the transaction; _txn must roll
        # back so no partial activation row sneaks in.
        with pytest.raises(KeyError):
            store.log_activation("ghost", "jp", 0.5, _ts())
        # The activations table should be untouched.
        with store._lock:
            n = store._conn.execute("SELECT COUNT(*) FROM dcn_activations;").fetchone()[0]
        assert n == 0

    def test_merge_unknown_dst_rolls_back_atomically(self, store: SqliteDCNStore) -> None:
        # merge() does its existence checks inside _txn; failure must
        # leave the graph fully intact.
        store.add_node(_concern("s"))
        store.add_node(_concern("x"))
        store.add_edge("s", "x", ConcernRelationType.ACTIVATES, weight=0.5)
        store.log_activation("s", "jp", 0.5, _ts())

        with pytest.raises(KeyError):
            store.merge("s", "missing")

        # State unchanged: src still alive, edge still there, activation still there.
        assert "s" in store
        assert store.edge_weight("s", "x", ConcernRelationType.ACTIVATES) == 0.5
        assert len(list(store.activation_log())) == 1


class TestThreading:
    def test_concurrent_writers_are_serialised(self) -> None:
        # The store advertises thread-safety via the RLock; pin it
        # by hammering nodes + activations from N threads and
        # checking the final counts.
        store = SqliteDCNStore(":memory:")
        try:
            threads = 6
            per_thread = 20

            # Pre-seed nodes so log_activation has something to
            # reference; keeping node creation single-threaded makes
            # the test about activation concurrency, not node-PK
            # races (which the memory backend doesn't really have
            # either since dict assignment is atomic under the GIL).
            for tid in range(threads):
                store.add_node(_concern(f"t{tid}"))

            def writer(tid: int) -> None:
                for j in range(per_thread):
                    store.log_activation(f"t{tid}", f"jp{j}", 0.5, _ts(j))

            workers = [threading.Thread(target=writer, args=(i,)) for i in range(threads)]
            for t in workers:
                t.start()
            for t in workers:
                t.join()

            total = list(store.activation_log())
            assert len(total) == threads * per_thread
        finally:
            store.close()


# ---------------------------------------------------------------------------
# Memory-backend parity tests
#
# Direct comparison against MemoryDCNStore so any future divergence on
# either side trips immediately. Same fixture, same operation order,
# same assertion. Mirrors the search() parity test from PR-13.
# ---------------------------------------------------------------------------


class TestMemoryParity:
    def test_neighbors_parity_after_mixed_inserts_and_removals(self) -> None:
        mem = MemoryDCNStore()
        sql = SqliteDCNStore(":memory:")
        try:
            for cid in "abcd":
                mem.add_node(_concern(cid))
                sql.add_node(_concern(cid))
            ops: list[tuple[str, str, ConcernRelationType]] = [
                ("a", "b", ConcernRelationType.ACTIVATES),
                ("a", "c", ConcernRelationType.SUPPRESSES),
                ("a", "b", ConcernRelationType.CONSTRAINS),
                ("a", "d", ConcernRelationType.ACTIVATES),
            ]
            for s, d, rel in ops:
                mem.add_edge(s, d, rel)
                sql.add_edge(s, d, rel)
            assert mem.neighbors("a") == sql.neighbors("a")
            assert mem.neighbors("a", relation_type=ConcernRelationType.ACTIVATES) == sql.neighbors(
                "a", relation_type=ConcernRelationType.ACTIVATES
            )
        finally:
            sql.close()

    def test_merge_parity_with_collisions_and_self_loops(self) -> None:
        # The combination test: collisions, self-loops, plus
        # untouched edges that pass through unchanged. If sqlite
        # drifts on first-occurrence-seq tracking, this will catch it.
        edges = [
            ("s", "x", ConcernRelationType.ACTIVATES, 0.5),
            ("y", "s", ConcernRelationType.CONSTRAINS, 0.7),
            ("d", "x", ConcernRelationType.ACTIVATES, 0.3),
            ("s", "d", ConcernRelationType.ACTIVATES, 0.4),  # self-loop after merge
            ("y", "x", ConcernRelationType.ACTIVATES, 0.6),  # untouched
        ]
        mem = MemoryDCNStore()
        sql = SqliteDCNStore(":memory:")
        try:
            for cid in "sdxy":
                mem.add_node(_concern(cid))
                sql.add_node(_concern(cid))
            for s, d, rel, w in edges:
                mem.add_edge(s, d, rel, weight=w)
                sql.add_edge(s, d, rel, weight=w)
            mem.log_activation("s", "jp1", 0.6, _ts(1))
            sql.log_activation("s", "jp1", 0.6, _ts(1))

            mem.merge("s", "d")
            sql.merge("s", "d")

            # Same edges, same weights.
            for s, d, rel in [
                ("d", "x", ConcernRelationType.ACTIVATES),
                ("y", "d", ConcernRelationType.CONSTRAINS),
                ("y", "x", ConcernRelationType.ACTIVATES),
            ]:
                assert mem.edge_weight(s, d, rel) == sql.edge_weight(s, d, rel)
            assert mem.edge_count() == sql.edge_count()

            # Same neighbor order.
            assert mem.neighbors("d") == sql.neighbors("d")
            assert mem.neighbors("y") == sql.neighbors("y")

            # Same activation reattribution.
            mem_recs = [(r["concern_id"], r["joinpoint_id"]) for r in mem.activation_log()]
            sql_recs = [(r["concern_id"], r["joinpoint_id"]) for r in sql.activation_log()]
            assert mem_recs == sql_recs
        finally:
            sql.close()

    @pytest.mark.parametrize("limit", [None, 1, 3, 5, 10, 0, -1])
    def test_activation_log_limit_parity(self, limit: int | None) -> None:
        mem = MemoryDCNStore()
        sql = SqliteDCNStore(":memory:")
        try:
            mem.add_node(_concern("a"))
            sql.add_node(_concern("a"))
            for i in range(5):
                mem.log_activation("a", f"jp{i}", 0.1 * i, _ts(i))
                sql.log_activation("a", f"jp{i}", 0.1 * i, _ts(i))

            mem_ids = [r["joinpoint_id"] for r in mem.activation_log(limit=limit)]
            sql_ids = [r["joinpoint_id"] for r in sql.activation_log(limit=limit)]
            assert mem_ids == sql_ids
        finally:
            sql.close()
