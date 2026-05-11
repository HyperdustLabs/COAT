"""SQLite-backed :class:`DCNStore` implementation (M3 PR-14).

The first non-volatile :class:`DCNStore`. Identical contract to
:class:`MemoryDCNStore` — same protocol, same node / edge / activation
semantics — so hosts can swap the in-memory backend for the SQLite
one with a single constructor change.

Storage model
-------------

* **Nodes** (``dcn_nodes``) round-trip the full :class:`Concern`
  envelope through a ``body_json`` column with the ``lifecycle_state``
  hot field projected for cheap archive lookups.  Node mutation
  (``archive``) re-derives ``body_json`` from the loaded model so
  the stored payload stays the source of truth — no drift between
  the projected column and the JSON body.
* **Edges** (``dcn_edges``) use a composite primary key on
  ``(src, dst, relation_type)`` so multiple distinct relations
  between the same pair coexist (the ``activates`` and
  ``constrains`` use case).  Foreign-key cascades on both endpoints
  mean removing a node automatically drops its dangling edges.
  Each edge gets a monotone ``seq`` that drives ``neighbors()``
  iteration order — mirroring how ``MemoryDCNStore`` walks
  ``self._edges`` in dict-insertion order.
* **Activations** (``dcn_activations``) are an append-only event
  log keyed by an ``AUTOINCREMENT`` ``seq``.  ``activation_log
  (limit=N)`` returns the *last* ``N`` records in chronological
  (not reverse) order — same as the memory backend's
  ``snapshot[-limit:]``.

Concurrency
-----------

A single long-lived ``sqlite3.Connection`` is held by each store
instance, guarded by an ``RLock``.  Same setup as
:class:`SqliteConcernStore`: ``check_same_thread=False``,
``isolation_level=None`` (autocommit, transactions driven via
explicit ``BEGIN``/``COMMIT``), ``journal_mode=WAL`` (graceful
fallback), ``foreign_keys=ON``.

Path resolution
---------------

``path`` accepts ``":memory:"`` (default) or a filesystem path.
Parent directories are auto-created on first construction so a host
pointing at ``/var/lib/coat/dcn.db`` doesn't have to ``mkdir -p``
themselves.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterable, Iterator
from contextlib import contextmanager, suppress
from datetime import datetime
from pathlib import Path
from typing import Any

from COAT_runtime_core.ports import DCNStore
from COAT_runtime_protocol import Concern, ConcernRelationType, LifecycleState

from ._schema import DCN_SCHEMA_VERSION, bootstrap_dcn_sql

_IN_MEMORY = ":memory:"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rel_key(rel: ConcernRelationType | str) -> str:
    """Normalise a relation_type to its string form.

    Mirrors :func:`COAT_runtime_storage.memory.dcn_store._rel_key` so
    a host that switches backends sees the same comparison semantics
    (the protocol envelopes have ``use_enum_values=True`` so on the
    wire these are already strings).
    """
    return rel.value if isinstance(rel, ConcernRelationType) else rel


def _node_to_row(concern: Concern) -> tuple[str, str, str]:
    payload = concern.model_dump(mode="json")
    body_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return (concern.id, concern.lifecycle_state, body_json)


def _node_from_row(row: sqlite3.Row) -> Concern:
    return Concern.model_validate(json.loads(row["body_json"]))


def _activation_record(row: sqlite3.Row) -> dict[str, Any]:
    """Rebuild a memory-backend-shaped activation dict.

    Memory stores raw ``datetime`` instances; sqlite stores ISO
    strings. We parse back to a tz-aware ``datetime`` so callers
    that compare ``rec["ts"]`` against another ``datetime`` get
    type parity for free.
    """
    return {
        "concern_id": row["concern_id"],
        "joinpoint_id": row["joinpoint_id"],
        "score": float(row["score"]),
        "ts": datetime.fromisoformat(row["ts"]),
    }


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class SqliteDCNStore(DCNStore):
    """Single-process, single-file SQLite-backed Deep Concern Network store.

    Parameters
    ----------
    path:
        Database location. ``":memory:"`` (the default) makes a
        per-instance ephemeral DB; any other ``str`` or
        :class:`pathlib.Path` is opened (and created on first use)
        as a file. The parent directory is auto-created.

    Example
    -------
    >>> from COAT_runtime_storage.sqlite import SqliteDCNStore
    >>> dcn = SqliteDCNStore("/var/lib/coat/dcn.db")
    >>> dcn.add_node(my_concern)
    >>> dcn.add_edge("a", "b", ConcernRelationType.ACTIVATES, weight=0.7)
    >>> # ...later...
    >>> dcn.close()
    """

    def __init__(self, path: str | Path = _IN_MEMORY) -> None:
        self._path = self._resolve_path(path)
        self._lock = threading.RLock()
        self._conn = self._open(self._path)
        self._bootstrap()

    # ------------------------------------------------------------------
    # Construction / teardown
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_path(path: str | Path) -> str:
        # Same logic as SqliteConcernStore — duplicated rather than
        # imported because importing across two store modules would
        # create a circular-import gotcha when the package is
        # extended in PR-15 (jsonl). Tiny enough to not warrant a
        # _db.py refactor at this milestone.
        if isinstance(path, Path):
            path.parent.mkdir(parents=True, exist_ok=True)
            return str(path)
        if path == _IN_MEMORY:
            return _IN_MEMORY
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _open(path: str) -> sqlite3.Connection:
        conn = sqlite3.connect(
            path,
            check_same_thread=False,
            isolation_level=None,
            detect_types=0,
        )
        conn.row_factory = sqlite3.Row
        with suppress(sqlite3.DatabaseError):
            conn.execute("PRAGMA journal_mode = WAL;")
        # FK enforcement is critical: without it the
        # ``ON DELETE CASCADE`` clauses are silent no-ops and
        # ``remove_node`` would leave dangling edges + activation
        # rows. PRAGMA is per-connection in sqlite, so we set it on
        # every open.
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _bootstrap(self) -> None:
        # ``executescript`` issues its own implicit COMMIT before
        # running, so we drive it directly without a manual
        # BEGIN/COMMIT (mirrors SqliteConcernStore._bootstrap).
        with self._lock:
            self._conn.executescript(bootstrap_dcn_sql())
            self._conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?);",
                ("dcn_schema_version", str(DCN_SCHEMA_VERSION)),
            )

    @contextmanager
    def _txn(self) -> Iterator[sqlite3.Cursor]:
        cur = self._conn.cursor()
        cur.execute("BEGIN;")
        try:
            yield cur
            cur.execute("COMMIT;")
        except Exception:
            cur.execute("ROLLBACK;")
            raise
        finally:
            cur.close()

    def close(self) -> None:
        """Release the underlying connection. Idempotent."""
        with self._lock, suppress(sqlite3.Error):
            self._conn.close()

    def __enter__(self) -> SqliteDCNStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @property
    def path(self) -> str:
        return self._path

    # ------------------------------------------------------------------
    # Nodes
    # ------------------------------------------------------------------

    def add_node(self, concern: Concern) -> None:
        if not concern.id:
            raise ValueError("Concern.id must be a non-empty string")
        node_id, lifecycle, body_json = _node_to_row(concern)
        with self._lock, self._txn() as cur:
            cur.execute(
                """
                INSERT INTO dcn_nodes (id, lifecycle_state, body_json)
                VALUES (?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    lifecycle_state = excluded.lifecycle_state,
                    body_json       = excluded.body_json;
                """,
                (node_id, lifecycle, body_json),
            )

    def remove_node(self, concern_id: str) -> None:
        # FK cascades take care of edges (both directions, since the
        # FK is declared on src AND dst) and activation rows.
        # Idempotent because DELETE on a missing PK is a no-op.
        with self._lock, self._txn() as cur:
            cur.execute("DELETE FROM dcn_nodes WHERE id = ?;", (concern_id,))

    def get_node(self, concern_id: str) -> Concern | None:
        """Convenience accessor — not part of the port, useful for tests."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT body_json FROM dcn_nodes WHERE id = ?;",
                (concern_id,),
            )
            row = cur.fetchone()
        return _node_from_row(row) if row is not None else None

    # ------------------------------------------------------------------
    # Edges
    # ------------------------------------------------------------------

    def add_edge(
        self,
        src: str,
        dst: str,
        relation_type: ConcernRelationType,
        *,
        weight: float = 1.0,
    ) -> None:
        if not 0.0 <= weight <= 1.0:
            raise ValueError(f"weight must be in [0.0, 1.0], got {weight}")
        rel = _rel_key(relation_type)
        with self._lock, self._txn() as cur:
            # We could let the FK constraint catch missing nodes,
            # but the memory backend raises ``KeyError`` with a
            # specific message. Mirror that exactly so a host
            # switching backends sees the same exception type and
            # message text.
            cur.execute("SELECT 1 FROM dcn_nodes WHERE id = ?;", (src,))
            if cur.fetchone() is None:
                raise KeyError(f"unknown src concern: {src!r}")
            cur.execute("SELECT 1 FROM dcn_nodes WHERE id = ?;", (dst,))
            if cur.fetchone() is None:
                raise KeyError(f"unknown dst concern: {dst!r}")

            # Allocate a seq only on first insert; updating an
            # existing edge keeps its original seq (so ``add_edge``
            # twice with different weights doesn't reorder
            # ``neighbors()`` output — same as the memory backend's
            # dict-update semantics).
            cur.execute(
                "SELECT seq FROM dcn_edges WHERE src = ? AND dst = ? AND relation_type = ?;",
                (src, dst, rel),
            )
            existing = cur.fetchone()
            if existing is not None:
                seq = existing["seq"]
            else:
                cur.execute("SELECT COALESCE(MAX(seq), 0) + 1 AS next_seq FROM dcn_edges;")
                seq = cur.fetchone()["next_seq"]

            cur.execute(
                """
                INSERT INTO dcn_edges (src, dst, relation_type, weight, seq)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(src, dst, relation_type) DO UPDATE SET
                    weight = excluded.weight;
                """,
                (src, dst, rel, weight, seq),
            )

    def remove_edge(self, src: str, dst: str, relation_type: ConcernRelationType) -> None:
        rel = _rel_key(relation_type)
        with self._lock, self._txn() as cur:
            cur.execute(
                "DELETE FROM dcn_edges WHERE src = ? AND dst = ? AND relation_type = ?;",
                (src, dst, rel),
            )

    def neighbors(
        self,
        concern_id: str,
        *,
        relation_type: ConcernRelationType | None = None,
    ) -> list[str]:
        # The memory backend dedupes ``dst`` and yields each in the
        # order of its FIRST appearance in the edges-iteration. We
        # mirror that with ``GROUP BY dst, MIN(seq)`` — first
        # insertion wins, even if the same dst appears later via a
        # different relation_type.
        params: list[Any] = [concern_id]
        rel_clause = ""
        if relation_type is not None:
            rel_clause = " AND relation_type = ?"
            params.append(_rel_key(relation_type))
        sql = f"""
            SELECT dst, MIN(seq) AS first_seq
            FROM dcn_edges
            WHERE src = ?{rel_clause}
            GROUP BY dst
            ORDER BY first_seq ASC;
        """
        with self._lock:
            cur = self._conn.execute(sql, params)
            return [row["dst"] for row in cur.fetchall()]

    def edge_weight(self, src: str, dst: str, relation_type: ConcernRelationType) -> float | None:
        """Convenience accessor — not part of the port, useful for tests."""
        with self._lock:
            cur = self._conn.execute(
                """
                SELECT weight FROM dcn_edges
                WHERE src = ? AND dst = ? AND relation_type = ?;
                """,
                (src, dst, _rel_key(relation_type)),
            )
            row = cur.fetchone()
        return float(row["weight"]) if row is not None else None

    def edge_count(self) -> int:
        with self._lock:
            cur = self._conn.execute("SELECT COUNT(*) AS n FROM dcn_edges;")
            return int(cur.fetchone()["n"])

    # ------------------------------------------------------------------
    # Activation history
    # ------------------------------------------------------------------

    def log_activation(
        self,
        concern_id: str,
        joinpoint_id: str,
        score: float,
        ts: datetime,
    ) -> None:
        if not 0.0 <= score <= 1.0:
            raise ValueError(f"score must be in [0.0, 1.0], got {score}")
        with self._lock, self._txn() as cur:
            cur.execute("SELECT 1 FROM dcn_nodes WHERE id = ?;", (concern_id,))
            if cur.fetchone() is None:
                raise KeyError(f"unknown concern: {concern_id!r}")
            cur.execute(
                """
                INSERT INTO dcn_activations (concern_id, joinpoint_id, score, ts)
                VALUES (?, ?, ?, ?);
                """,
                (concern_id, joinpoint_id, score, ts.isoformat()),
            )

    def activation_log(
        self,
        concern_id: str | None = None,
        *,
        limit: int | None = None,
    ) -> Iterable[dict]:
        # Match the memory backend exactly: a ``limit <= 0`` returns
        # an empty iterable (NOT all-records-then-truncate).
        if limit is not None and limit <= 0:
            return []

        params: list[Any] = []
        where = ""
        if concern_id is not None:
            where = "WHERE concern_id = ?"
            params.append(concern_id)

        if limit is None:
            sql = f"""
                SELECT concern_id, joinpoint_id, score, ts
                FROM dcn_activations
                {where}
                ORDER BY seq ASC;
            """
        else:
            # ``snapshot[-limit:]`` semantics: grab the last ``limit``
            # rows, then return them in chronological order. Done
            # with a subquery so the outer SELECT can re-sort
            # ascending without losing the limit.
            sql = f"""
                SELECT concern_id, joinpoint_id, score, ts
                FROM (
                    SELECT seq, concern_id, joinpoint_id, score, ts
                    FROM dcn_activations
                    {where}
                    ORDER BY seq DESC
                    LIMIT ?
                )
                ORDER BY seq ASC;
            """
            params.append(limit)

        with self._lock:
            cur = self._conn.execute(sql, params)
            rows = cur.fetchall()
        return [_activation_record(row) for row in rows]

    # ------------------------------------------------------------------
    # Housekeeping
    # ------------------------------------------------------------------

    def merge(self, src: str, dst: str) -> None:
        """Rewire every edge / activation pointing at ``src`` to ``dst``.

        Mirrors :meth:`MemoryDCNStore.merge`:

        * Edges are rewired in iteration order; on collision with an
          existing rewired key, the higher of the two weights wins
          and the *first* occurrence's ``seq`` is preserved (so
          ``neighbors()`` keeps its first-appearance ordering).
        * Self-loops created by rewiring (``src→dst`` becomes
          ``dst→dst``) are dropped silently.
        * Activations are reattributed: their ``concern_id`` flips
          from ``src`` to ``dst``.
        * The ``src`` node is then removed; FK cascade would also
          take its remaining edges, but we've already rewired them.

        The whole operation runs inside a single transaction so a
        concurrent reader either sees the pre-merge or the post-merge
        graph, never an intermediate state.
        """
        if src == dst:
            return
        with self._lock, self._txn() as cur:
            # Existence checks first so we raise the same KeyError
            # the memory backend raises, before doing any writes.
            cur.execute("SELECT 1 FROM dcn_nodes WHERE id = ?;", (src,))
            if cur.fetchone() is None:
                raise KeyError(f"unknown src concern: {src!r}")
            cur.execute("SELECT 1 FROM dcn_nodes WHERE id = ?;", (dst,))
            if cur.fetchone() is None:
                raise KeyError(f"unknown dst concern: {dst!r}")

            cur.execute(
                """
                SELECT src, dst, relation_type, weight, seq
                FROM dcn_edges
                ORDER BY seq ASC;
                """
            )
            edges = cur.fetchall()

            # Rewired key → (max_weight, min_seq) — preserves the
            # first-occurrence position the memory backend's dict
            # rebuild gives us for free.
            rewired: dict[tuple[str, str, str], tuple[float, int]] = {}
            for row in edges:
                s = dst if row["src"] == src else row["src"]
                d = dst if row["dst"] == src else row["dst"]
                if s == d:
                    continue
                key = (s, d, row["relation_type"])
                if key in rewired:
                    old_w, old_seq = rewired[key]
                    rewired[key] = (max(old_w, float(row["weight"])), old_seq)
                else:
                    rewired[key] = (float(row["weight"]), int(row["seq"]))

            cur.execute("DELETE FROM dcn_edges;")
            if rewired:
                cur.executemany(
                    """
                    INSERT INTO dcn_edges (src, dst, relation_type, weight, seq)
                    VALUES (?, ?, ?, ?, ?);
                    """,
                    [(s, d, rel, w, seq) for (s, d, rel), (w, seq) in rewired.items()],
                )

            cur.execute(
                "UPDATE dcn_activations SET concern_id = ? WHERE concern_id = ?;",
                (dst, src),
            )
            cur.execute("DELETE FROM dcn_nodes WHERE id = ?;", (src,))

    def archive(self, concern_id: str) -> None:
        """Mark a node's lifecycle_state as ``archived``.

        Both the projected ``lifecycle_state`` column AND the
        ``body_json`` payload are updated so the source-of-truth body
        and the hot column never disagree.
        """
        with self._lock, self._txn() as cur:
            cur.execute(
                "SELECT body_json FROM dcn_nodes WHERE id = ?;",
                (concern_id,),
            )
            row = cur.fetchone()
            if row is None:
                # Idempotent: the memory backend does the same.
                return
            concern = Concern.model_validate(json.loads(row["body_json"]))
            concern.lifecycle_state = LifecycleState.ARCHIVED.value  # type: ignore[assignment]
            payload = concern.model_dump(mode="json")
            body_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
            cur.execute(
                """
                UPDATE dcn_nodes
                SET lifecycle_state = ?, body_json = ?
                WHERE id = ?;
                """,
                (LifecycleState.ARCHIVED.value, body_json, concern_id),
            )

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        with self._lock:
            cur = self._conn.execute("SELECT COUNT(*) AS n FROM dcn_nodes;")
            return int(cur.fetchone()["n"])

    def __contains__(self, concern_id: object) -> bool:
        if not isinstance(concern_id, str):
            return False
        with self._lock:
            cur = self._conn.execute(
                "SELECT 1 FROM dcn_nodes WHERE id = ? LIMIT 1;",
                (concern_id,),
            )
            return cur.fetchone() is not None


__all__ = ["SqliteDCNStore"]
