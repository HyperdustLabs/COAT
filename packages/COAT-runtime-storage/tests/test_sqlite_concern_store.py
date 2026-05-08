"""Behavioural tests for :class:`SqliteConcernStore` (M3 PR-13).

The SQLite backend must behave identically to the in-memory one
for every public-API call — same protocol, same defensive-copy
semantics, same insertion-order guarantee. The first half of this
file is a straight port of ``test_memory_concern_store.py`` with
``MemoryConcernStore`` swapped for ``SqliteConcernStore``; the
second half pins SQLite-specific behaviour (file persistence,
schema bootstrap idempotency, FK cascade, transaction rollback,
threaded access) that the memory backend can't exhibit.

All tests run against ``:memory:`` databases unless they
explicitly need to test on-disk persistence — keeps the suite
hermetic and fast (~50 ms for the whole file).
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

import pytest
from COAT_runtime_core.ports import ConcernStore
from COAT_runtime_protocol import Concern, ConcernKind, LifecycleState
from COAT_runtime_storage.memory import MemoryConcernStore
from COAT_runtime_storage.sqlite import (
    SCHEMA_VERSION,
    SqliteConcernStore,
    bootstrap_sql,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _concern(
    cid: str,
    *,
    name: str | None = None,
    description: str = "",
    kind: ConcernKind = ConcernKind.CONCERN,
    tags: list[str] | None = None,
    lifecycle: LifecycleState = LifecycleState.CREATED,
    generated_type: str | None = None,
) -> Concern:
    return Concern(
        id=cid,
        kind=kind,
        name=name or cid,
        description=description,
        generated_tags=tags or [],
        lifecycle_state=lifecycle,
        generated_type=generated_type,
    )


@pytest.fixture
def store() -> SqliteConcernStore:
    """Per-test ``:memory:`` store. Closed automatically by GC.

    We don't bother with explicit close() in the fixture because an
    in-memory connection is freed when the Python object is — and
    the test would notice if any state leaked between tests anyway
    (each fixture call hands back a fresh store).
    """
    return SqliteConcernStore(":memory:")


# ---------------------------------------------------------------------------
# Protocol shape
# ---------------------------------------------------------------------------


class TestProtocol:
    def test_implements_concern_store_protocol(self, store: SqliteConcernStore) -> None:
        assert isinstance(store, ConcernStore)

    def test_default_path_is_in_memory(self) -> None:
        assert SqliteConcernStore().path == ":memory:"

    def test_path_argument_is_preserved(self, tmp_path: Path) -> None:
        db = tmp_path / "concerns.db"
        s = SqliteConcernStore(db)
        try:
            assert s.path == str(db)
        finally:
            s.close()


# ---------------------------------------------------------------------------
# CRUD (port of MemoryConcernStore tests)
# ---------------------------------------------------------------------------


class TestCRUD:
    def test_upsert_returns_independent_copy(self, store: SqliteConcernStore) -> None:
        original = _concern("c1", name="alpha")
        returned = store.upsert(original)
        assert returned.id == "c1"
        assert returned is not original

        # Mutating the returned snapshot must not affect the store.
        returned.name = "mutated-by-caller"
        roundtrip = store.get("c1")
        assert roundtrip is not None
        assert roundtrip.name == "alpha"

    def test_get_returns_independent_copy(self, store: SqliteConcernStore) -> None:
        store.upsert(_concern("c1", name="alpha"))
        a = store.get("c1")
        b = store.get("c1")
        assert a == b
        assert a is not b
        assert a is not None
        a.name = "tampered"
        again = store.get("c1")
        assert again is not None
        assert again.name == "alpha"

    def test_get_missing_returns_none(self, store: SqliteConcernStore) -> None:
        assert store.get("nope") is None

    def test_upsert_overwrites_existing(self, store: SqliteConcernStore) -> None:
        store.upsert(_concern("c1", name="v1"))
        store.upsert(_concern("c1", name="v2"))
        latest = store.get("c1")
        assert latest is not None
        assert latest.name == "v2"
        assert len(store) == 1

    def test_upsert_rejects_empty_id(self, store: SqliteConcernStore) -> None:
        with pytest.raises(ValueError, match="id"):
            store.upsert(_concern(""))

    def test_delete_is_idempotent(self, store: SqliteConcernStore) -> None:
        store.upsert(_concern("c1"))
        store.delete("c1")
        store.delete("c1")
        assert store.get("c1") is None


# ---------------------------------------------------------------------------
# Listing & filters (port + lifecycle filter as parameterized cases)
# ---------------------------------------------------------------------------


class TestListing:
    def test_list_preserves_insertion_order(self, store: SqliteConcernStore) -> None:
        for i in range(5):
            store.upsert(_concern(f"c{i}", name=f"n{i}"))
        ids = [c.id for c in store.list()]
        assert ids == ["c0", "c1", "c2", "c3", "c4"]

    def test_upsert_existing_concern_keeps_seq(self, store: SqliteConcernStore) -> None:
        # Memory backend pins this implicitly via dict insertion
        # order; sqlite does it explicitly through the ``seq``
        # column. Re-upserting an existing id must NOT push that
        # concern to the end of the list.
        for i in range(3):
            store.upsert(_concern(f"c{i}"))
        store.upsert(_concern("c0", name="updated"))  # should stay at position 0
        ids = [c.id for c in store.list()]
        assert ids == ["c0", "c1", "c2"]

    def test_list_filters_combine_with_and(self, store: SqliteConcernStore) -> None:
        store.upsert(_concern("a", kind=ConcernKind.CONCERN, tags=["billing"]))
        store.upsert(_concern("b", kind=ConcernKind.CONCERN, tags=["billing", "fraud"]))
        store.upsert(_concern("m", kind=ConcernKind.META_CONCERN, tags=["billing"]))

        billing = {c.id for c in store.list(tag="billing")}
        assert billing == {"a", "b", "m"}

        concerns_only = {c.id for c in store.list(kind="concern")}
        assert concerns_only == {"a", "b"}

        intersect = {c.id for c in store.list(kind="concern", tag="fraud")}
        assert intersect == {"b"}

    def test_list_lifecycle_filter(self, store: SqliteConcernStore) -> None:
        store.upsert(_concern("a", lifecycle=LifecycleState.ACTIVE))
        store.upsert(_concern("b", lifecycle=LifecycleState.ARCHIVED))
        active = {c.id for c in store.list(lifecycle_state="active")}
        assert active == {"a"}

    def test_list_limit_truncates_after_filter(self, store: SqliteConcernStore) -> None:
        for i in range(10):
            store.upsert(_concern(f"c{i}", tags=["x"]))
        out = store.list(tag="x", limit=3)
        assert [c.id for c in out] == ["c0", "c1", "c2"]

    @pytest.mark.parametrize("bad_limit", [0, -1, -100])
    def test_list_non_positive_limit_returns_empty(
        self, store: SqliteConcernStore, bad_limit: int
    ) -> None:
        # The memory backend treats only ``limit < 0`` as empty, but
        # ``limit == 0`` was always semantically the same ("give me
        # zero results"). SQLite returns 0 rows for ``LIMIT 0`` so
        # they agree; we lock the behaviour here so a future memory
        # tweak doesn't drift.
        store.upsert(_concern("a"))
        assert store.list(limit=bad_limit) == []

    def test_list_tag_no_substring_match(self, store: SqliteConcernStore) -> None:
        # Side-table tag storage means ``tag="bill"`` MUST NOT match
        # ``"billing"``. The memory backend's ``tag in
        # generated_tags`` already rejects substrings; pin it here
        # so a future "use LIKE" optimisation doesn't break it.
        store.upsert(_concern("a", tags=["billing"]))
        store.upsert(_concern("b", tags=["bill"]))
        only_bill = [c.id for c in store.list(tag="bill")]
        assert only_bill == ["b"]

    def test_list_unknown_filter_value_returns_empty(self, store: SqliteConcernStore) -> None:
        store.upsert(_concern("a", kind=ConcernKind.CONCERN))
        assert store.list(kind="not-a-kind") == []


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


class TestSearch:
    def test_search_matches_name_and_description_case_insensitive(
        self, store: SqliteConcernStore
    ) -> None:
        store.upsert(_concern("a", name="Refund policy", description="when to issue refunds"))
        store.upsert(_concern("b", name="Greeting", description="how to greet customers"))
        store.upsert(_concern("c", name="Tax rules", description="VAT and refund interaction"))

        hits = {c.id for c in store.search("REFUND")}
        assert hits == {"a", "c"}

    @pytest.mark.parametrize("query", ["", " ", "\t", "\n   \t"])
    def test_search_empty_or_whitespace_returns_empty(
        self, store: SqliteConcernStore, query: str
    ) -> None:
        store.upsert(_concern("a", name="hi"))
        assert store.search(query) == []

    def test_search_respects_limit(self, store: SqliteConcernStore) -> None:
        for i in range(5):
            store.upsert(_concern(f"c{i}", name=f"refund-{i}"))
        assert len(store.search("refund", limit=2)) == 2

    @pytest.mark.parametrize("bad_limit", [0, -1])
    def test_search_non_positive_limit_returns_empty(
        self, store: SqliteConcernStore, bad_limit: int
    ) -> None:
        store.upsert(_concern("a", name="refund"))
        assert store.search("refund", limit=bad_limit) == []

    def test_search_returns_in_insertion_order(self, store: SqliteConcernStore) -> None:
        # Pin the ordering so a future caller can rely on it for
        # stable test fixtures.
        store.upsert(_concern("a", name="refund alpha"))
        store.upsert(_concern("b", name="refund beta"))
        ids = [c.id for c in store.search("refund")]
        assert ids == ["a", "b"]

    # ------------------------------------------------------------------
    # LIKE-metacharacter regression tests
    #
    # Codex P2 on PR-13: a naive ``LIKE %{needle}%`` interpolation
    # treats ``%`` and ``_`` as SQL wildcards, so user queries
    # containing those characters silently match different rows than
    # the memory backend's literal ``in``-test. The fix escapes them
    # via ``LIKE ? ESCAPE '\\'``.
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        ("query", "expected_ids"),
        [
            # ``%`` must match a literal percent sign, not "everything".
            ("%", {"pct"}),
            # ``_`` must match a literal underscore, not "any one char".
            ("_", {"under"}),
            # Mixed: a real-world looking query.
            ("100%", {"pct"}),
            ("a_b", {"under"}),
            # Backslash is the escape char itself; a literal backslash
            # in the query must round-trip without breaking the next
            # character's escape.
            ("\\", {"slash"}),
            # No metacharacters → unchanged behaviour.
            ("plain", {"plain"}),
        ],
    )
    def test_search_treats_like_metacharacters_as_literals(
        self,
        store: SqliteConcernStore,
        query: str,
        expected_ids: set[str],
    ) -> None:
        store.upsert(_concern("pct", name="discount 100% off"))
        store.upsert(_concern("under", name="snake_case a_b naming"))
        store.upsert(_concern("slash", name=r"path\with\backslash"))
        store.upsert(_concern("plain", name="a plain refund"))
        store.upsert(_concern("noise1", name="nothing relevant here"))
        store.upsert(_concern("noise2", description="more noise"))

        hits = {c.id for c in store.search(query)}
        assert hits == expected_ids

    @pytest.mark.parametrize(
        "query",
        ["%", "_", "100%", "a_b", "%refund%", "\\", "plain"],
    )
    def test_search_parity_with_memory_backend(self, query: str) -> None:
        # The Concern store contract is "MemoryConcernStore is the
        # reference implementation". Pin parity directly so any
        # future divergence on either side trips this test rather
        # than silently shifting host behaviour.
        rows = [
            _concern("pct", name="discount 100% off"),
            _concern("under", name="snake_case a_b naming"),
            _concern("slash", name=r"path\with\backslash"),
            _concern("plain", name="a plain refund"),
            _concern("noise1", name="nothing relevant here"),
        ]
        mem = MemoryConcernStore()
        sql = SqliteConcernStore(":memory:")
        try:
            for c in rows:
                mem.upsert(c)
                sql.upsert(c)

            mem_ids = {c.id for c in mem.search(query)}
            sql_ids = {c.id for c in sql.search(query)}
            assert mem_ids == sql_ids, (
                f"backend mismatch on {query!r}: memory={mem_ids} sqlite={sql_ids}"
            )
        finally:
            sql.close()


# ---------------------------------------------------------------------------
# Iteration & helpers
# ---------------------------------------------------------------------------


class TestIteration:
    def test_iter_all_yields_independent_copies(self, store: SqliteConcernStore) -> None:
        store.upsert(_concern("a", name="orig"))
        seen = list(store.iter_all())
        assert len(seen) == 1
        seen[0].name = "tampered"
        again = store.get("a")
        assert again is not None
        assert again.name == "orig"

    def test_iter_all_yields_in_insertion_order(self, store: SqliteConcernStore) -> None:
        for i in range(3):
            store.upsert(_concern(f"c{i}"))
        ids = [c.id for c in store.iter_all()]
        assert ids == ["c0", "c1", "c2"]

    def test_contains_and_len(self, store: SqliteConcernStore) -> None:
        assert "a" not in store
        store.upsert(_concern("a"))
        assert "a" in store
        assert 123 not in store  # type: ignore[operator]
        assert len(store) == 1
        store.clear()
        assert len(store) == 0

    def test_clear_drops_tags_too(self, store: SqliteConcernStore) -> None:
        # If clear() forgets the side-table, list(tag=...) would
        # silently keep returning hits even though the parent
        # concerns are gone — exactly the kind of bug the test
        # name is meant to keep in mind.
        store.upsert(_concern("a", tags=["billing"]))
        store.clear()
        assert store.list(tag="billing") == []


# ---------------------------------------------------------------------------
# SQLite-specific: persistence, FK cascade, schema, transactions, threading
# ---------------------------------------------------------------------------


class TestPersistence:
    def test_concerns_survive_close_and_reopen(self, tmp_path: Path) -> None:
        # The whole point of this backend.
        db = tmp_path / "concerns.db"
        s1 = SqliteConcernStore(db)
        s1.upsert(
            _concern(
                "a",
                name="durable",
                description="must round-trip",
                tags=["billing", "fraud"],
                lifecycle=LifecycleState.REINFORCED,
                generated_type="safety_rule",
            )
        )
        s1.close()

        s2 = SqliteConcernStore(db)
        try:
            survived = s2.get("a")
            assert survived is not None
            assert survived.name == "durable"
            assert survived.description == "must round-trip"
            assert sorted(survived.generated_tags) == ["billing", "fraud"]
            assert survived.lifecycle_state == "reinforced"
            assert survived.generated_type == "safety_rule"
            # The tag side-table must rehydrate too.
            assert {c.id for c in s2.list(tag="billing")} == {"a"}
        finally:
            s2.close()

    def test_path_parent_dir_is_auto_created(self, tmp_path: Path) -> None:
        # Codex / future-self protection: a host that points the
        # store at ``/var/lib/coat/concerns.db`` shouldn't have to
        # mkdir -p first. We auto-create the parent.
        nested = tmp_path / "deep" / "nested" / "path" / "concerns.db"
        s = SqliteConcernStore(nested)
        try:
            assert nested.parent.exists()
        finally:
            s.close()

    def test_close_is_idempotent(self) -> None:
        s = SqliteConcernStore(":memory:")
        s.close()
        s.close()  # second call must not raise

    def test_context_manager_closes_on_exit(self, tmp_path: Path) -> None:
        db = tmp_path / "concerns.db"
        with SqliteConcernStore(db) as s:
            s.upsert(_concern("a"))
            assert "a" in s
        # The file persists after the with-block exits.
        assert db.exists()
        # And re-opening still finds the concern.
        with SqliteConcernStore(db) as s2:
            assert "a" in s2


class TestSchema:
    def test_bootstrap_is_idempotent(self, tmp_path: Path) -> None:
        # Re-opening an existing DB must not error — the
        # ``CREATE TABLE IF NOT EXISTS`` family handles that —
        # and the row count must be preserved.
        db = tmp_path / "concerns.db"
        with SqliteConcernStore(db) as s1:
            s1.upsert(_concern("a"))
            assert len(s1) == 1
        with SqliteConcernStore(db) as s2:
            assert len(s2) == 1

    def test_schema_version_recorded_in_meta(self, tmp_path: Path) -> None:
        db = tmp_path / "concerns.db"
        s = SqliteConcernStore(db)
        try:
            with sqlite3.connect(db) as raw:
                row = raw.execute("SELECT value FROM meta WHERE key = 'schema_version';").fetchone()
            assert row is not None
            assert int(row[0]) == SCHEMA_VERSION
        finally:
            s.close()

    def test_bootstrap_sql_creates_expected_tables(self, tmp_path: Path) -> None:
        # Sanity check on the DDL string itself — nice for someone
        # who wants to apply the schema by hand to an external DB.
        db = tmp_path / "ad-hoc.db"
        with sqlite3.connect(db) as raw:
            raw.executescript(bootstrap_sql())
            tables = {
                row[0]
                for row in raw.execute(
                    "SELECT name FROM sqlite_master WHERE type='table';"
                ).fetchall()
            }
        assert {"concerns", "concern_tags", "meta"} <= tables


class TestForeignKeys:
    def test_delete_cascades_to_tags(self, store: SqliteConcernStore) -> None:
        store.upsert(_concern("a", tags=["billing"]))
        store.upsert(_concern("b", tags=["billing"]))
        store.delete("a")
        # Only ``b`` remains in the tag side-table.
        assert {c.id for c in store.list(tag="billing")} == {"b"}

    def test_re_upsert_replaces_tag_set_atomically(self, store: SqliteConcernStore) -> None:
        # If we DELETE-then-INSERT for tags but a write fails between
        # the two, we'd leave the concern with no tags. The implementation
        # runs both inside a single _txn() so a rollback restores the
        # previous tag set; here we just verify the happy-path
        # replacement.
        store.upsert(_concern("a", tags=["billing", "fraud"]))
        store.upsert(_concern("a", tags=["loyalty"]))  # tag set replaced
        assert {c.id for c in store.list(tag="billing")} == set()
        assert {c.id for c in store.list(tag="fraud")} == set()
        assert {c.id for c in store.list(tag="loyalty")} == {"a"}


class TestTransactions:
    def test_upsert_rolls_back_on_error(self, store: SqliteConcernStore) -> None:
        # Force an integrity error by sneaking a bad row through the
        # private _txn() machinery, then verify pre-existing state is
        # unchanged. This is the canary that proves _txn() actually
        # rolls back on exception (instead of silently committing
        # whatever made it through).
        store.upsert(_concern("a", name="alpha"))

        with pytest.raises(sqlite3.IntegrityError), store._txn() as cur:
            # Insert a tag row pointing at a non-existent concern —
            # FK constraint must reject.
            cur.execute(
                "INSERT INTO concern_tags(concern_id, tag) VALUES (?, ?);",
                ("ghost", "x"),
            )

        # Original row untouched, no orphan tag persisted.
        survived = store.get("a")
        assert survived is not None
        assert survived.name == "alpha"
        assert store.list(tag="x") == []


class TestBodyJsonRoundtrip:
    def test_body_json_is_authoritative(self, store: SqliteConcernStore) -> None:
        # If a future migration projects a column wrong, the model
        # rebuilt from ``body_json`` must still match the original.
        # We poke a hot column with a stale value and then read
        # back — the returned model should reflect ``body_json``,
        # not the projected column.
        c = _concern("a", name="real-name")
        store.upsert(c)
        with store._lock:
            store._conn.execute(
                "UPDATE concerns SET name = ? WHERE id = ?;",
                ("stale-projected-name", "a"),
            )
        roundtrip = store.get("a")
        assert roundtrip is not None
        assert roundtrip.name == "real-name"

    def test_body_json_is_pretty_jsonable(self, store: SqliteConcernStore) -> None:
        # Stored payload must be valid JSON. Pin this so a future
        # change to the dump call (e.g. switching to ``ensure_ascii``)
        # still produces parseable output for ad-hoc CLI inspection.
        store.upsert(_concern("a", name="naïve", description="café"))
        with store._lock:
            row = store._conn.execute(
                "SELECT body_json FROM concerns WHERE id = ?;", ("a",)
            ).fetchone()
        payload = json.loads(row["body_json"])
        assert payload["id"] == "a"
        assert payload["name"] == "naïve"


class TestThreading:
    def test_concurrent_upserts_are_serialised(self) -> None:
        # The store is supposed to be safe to share across threads.
        # We hammer it with N threads each writing M concerns and
        # verify the final count + insertion-order invariants.
        store = SqliteConcernStore(":memory:")
        try:
            threads = 8
            per_thread = 25

            def writer(tid: int) -> None:
                for j in range(per_thread):
                    store.upsert(_concern(f"t{tid}-c{j}"))

            workers = [threading.Thread(target=writer, args=(i,)) for i in range(threads)]
            for t in workers:
                t.start()
            for t in workers:
                t.join()

            assert len(store) == threads * per_thread
            ids = [c.id for c in store.iter_all()]
            # Every id is unique.
            assert len(set(ids)) == len(ids)
        finally:
            store.close()
