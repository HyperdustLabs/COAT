"""SQLite-backed :class:`ConcernStore` implementation (M3 PR-13).

The first non-volatile :class:`ConcernStore`. Identical contract to
:class:`MemoryConcernStore` — same protocol, same defensive-copy
semantics, same insertion-order guarantee — so hosts can swap the
backend with a single constructor change.

Storage model
-------------

* The full :class:`Concern` is round-tripped via
  ``model_dump(mode="json") → json.dumps`` into the ``body_json``
  column.  This is the source of truth: nested envelopes (pointcut,
  advice, weaving policy, relations, activation_state, metrics, …)
  evolve over time and column-flattening every nested field would
  multiply the schema-migration surface for no real query payoff.
* A small set of *hot* fields is projected into typed columns
  (``kind``, ``name``, ``description``, ``generated_type``,
  ``lifecycle_state``) so SQL filters / searches use proper
  predicates and indexes.
* ``generated_tags`` is normalised into a ``concern_tags`` side-
  table with ``FOREIGN KEY ... ON DELETE CASCADE``.  ``list(tag=…)``
  is a JOIN — exact, not substring — and re-tagging on upsert is
  a short two-statement transaction (``DELETE`` + ``INSERT``).
* A monotonically-increasing ``seq`` column is allocated on first
  insert and preserved across upserts, giving the same byte-stable
  insertion order ``MemoryConcernStore`` already guarantees.

Concurrency
-----------

A single long-lived ``sqlite3.Connection`` is held by each store
instance, guarded by an ``RLock``.  The connection is opened with
``check_same_thread=False`` so the lock — not Python's GIL — is
the only thing serialising access.  ``journal_mode=WAL`` and
``foreign_keys=ON`` are set at open time.

The store is safe to use across threads inside one process; a
separate process should construct its own instance pointing at the
same file.

Path resolution
---------------

``path`` accepts:

* ``":memory:"`` (default) — ephemeral, per-instance database;
  ideal for tests.
* a ``str`` or :class:`pathlib.Path` — opened (and created on
  first use) at that location.

The parent directory is created on first construction so callers
don't have to ``mkdir -p`` themselves.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterable, Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any

from COAT_runtime_core.ports import ConcernStore
from COAT_runtime_protocol import Concern

from ._schema import SCHEMA_VERSION, bootstrap_sql

_IN_MEMORY = ":memory:"

# Backslash is the LIKE escape character below. Escape it FIRST so we
# don't double-escape the wildcards we add in the next pass. Order
# matters: ``str.replace`` is non-overlapping, so a naive
# ``replace("%", r"\%")`` followed by ``replace("\\", r"\\\\")``
# would corrupt the wildcards we just inserted.
_LIKE_ESCAPE_CHAR = "\\"


def _escape_like(needle: str) -> str:
    """Escape SQL LIKE metacharacters in a substring.

    ``LIKE`` treats ``%`` (any run of chars) and ``_`` (one char) as
    wildcards. ``MemoryConcernStore.search`` does a plain Python
    ``in``-test, so to match backend parity we have to neutralise
    those metacharacters before interpolating the user query into
    the pattern. The escape character itself (``\\``) must also be
    escaped so a literal backslash in the query doesn't accidentally
    quote the next character.

    Used together with ``LIKE ? ESCAPE '\\\\'`` in the SQL.
    """
    return (
        needle.replace(_LIKE_ESCAPE_CHAR, _LIKE_ESCAPE_CHAR * 2)
        .replace("%", _LIKE_ESCAPE_CHAR + "%")
        .replace("_", _LIKE_ESCAPE_CHAR + "_")
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_row(concern: Concern, *, seq: int) -> tuple[Any, ...]:
    """Project a Concern into the column tuple used for INSERT/UPDATE."""
    payload = concern.model_dump(mode="json")
    body_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return (
        concern.id,
        seq,
        concern.kind,
        concern.name,
        concern.description or "",
        concern.generated_type,
        concern.lifecycle_state,
        body_json,
        payload.get("created_at"),
        payload.get("updated_at"),
    )


def _from_row(row: sqlite3.Row | tuple[Any, ...]) -> Concern:
    """Rebuild a Concern from its stored ``body_json``.

    The hot columns are intentionally ignored on read — ``body_json``
    is the source of truth, and projecting from anywhere else would
    risk drift if a future migration touches one column but forgets
    the others.
    """
    body_json = row["body_json"] if isinstance(row, sqlite3.Row) else row[7]
    return Concern.model_validate(json.loads(body_json))


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class SqliteConcernStore(ConcernStore):
    """Single-process, single-file SQLite-backed Concern store.

    Parameters
    ----------
    path:
        Database location. ``":memory:"`` (the default) makes a
        per-instance ephemeral DB; any other ``str`` or
        :class:`pathlib.Path` is opened (and created on first use)
        as a file. The parent directory is auto-created.

    Example
    -------
    >>> from COAT_runtime_storage.sqlite import SqliteConcernStore
    >>> store = SqliteConcernStore("/var/lib/coat/concerns.db")
    >>> store.upsert(my_concern)
    >>> # ...later...
    >>> store.close()
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
        if isinstance(path, Path):
            path.parent.mkdir(parents=True, exist_ok=True)
            return str(path)
        if path == _IN_MEMORY:
            return _IN_MEMORY
        # ``str`` path — make sure the parent exists. We deliberately
        # do this after the in-memory short-circuit so a literal
        # ":memory:" never hits the filesystem.
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _open(path: str) -> sqlite3.Connection:
        # ``check_same_thread=False`` because the RLock above is what
        # actually serialises concurrent access; we don't want sqlite
        # second-guessing a properly-locked caller.
        # ``isolation_level=None`` switches the connection into
        # autocommit mode so we can drive transactions explicitly via
        # BEGIN/COMMIT — that lets ``upsert`` group its concerns +
        # concern_tags writes atomically without sqlite emitting
        # extra implicit commits.
        conn = sqlite3.connect(
            path,
            check_same_thread=False,
            isolation_level=None,
            detect_types=0,
        )
        conn.row_factory = sqlite3.Row
        # WAL is a no-op for ``:memory:`` databases (which are always
        # MEMORY journal mode); harmless to attempt. Some unusual
        # environments forbid WAL (e.g. NFS) — falling back to the
        # default journal mode keeps the store usable; the user only
        # sees the error if they explicitly query the pragma later.
        with suppress(sqlite3.DatabaseError):
            conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _bootstrap(self) -> None:
        # ``executescript`` issues its own implicit COMMIT before
        # running the script body (sqlite3 docs), so we deliberately
        # do NOT wrap this in ``_txn`` — the manual BEGIN/COMMIT
        # would race with the script's own transaction control. The
        # DDL bundle is idempotent (CREATE TABLE IF NOT EXISTS), so
        # running it outside a transaction is safe.
        with self._lock:
            self._conn.executescript(bootstrap_sql())
            self._conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?);",
                ("schema_version", str(SCHEMA_VERSION)),
            )

    @contextmanager
    def _txn(self) -> Iterator[sqlite3.Cursor]:
        """Run a block inside a single ``BEGIN`` / ``COMMIT`` window.

        The connection is in autocommit mode (``isolation_level=None``)
        so we drive transactions explicitly. ``ROLLBACK`` on exception
        keeps the database consistent if a write fails halfway
        through.
        """
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
        """Release the underlying connection.

        Idempotent: calling ``close()`` twice is a no-op. After
        ``close()`` further mutator calls raise ``sqlite3.ProgrammingError``
        from the closed connection.
        """
        # Idempotent close — sqlite raises ``ProgrammingError`` on a
        # second close, which we deliberately swallow so callers can
        # treat ``close()`` as a safe finaliser.
        with self._lock, suppress(sqlite3.Error):
            self._conn.close()

    def __enter__(self) -> SqliteConcernStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @property
    def path(self) -> str:
        """Resolved database path (``":memory:"`` for in-memory stores)."""
        return self._path

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def upsert(self, concern: Concern) -> Concern:
        if not concern.id:
            raise ValueError("Concern.id must be a non-empty string")

        with self._lock, self._txn() as cur:
            cur.execute("SELECT seq FROM concerns WHERE id = ?;", (concern.id,))
            existing = cur.fetchone()
            if existing is not None:
                seq = existing["seq"]
            else:
                cur.execute("SELECT COALESCE(MAX(seq), 0) + 1 AS next_seq FROM concerns;")
                seq = cur.fetchone()["next_seq"]

            cur.execute(
                """
                INSERT INTO concerns (
                    id, seq, kind, name, description, generated_type,
                    lifecycle_state, body_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    kind            = excluded.kind,
                    name            = excluded.name,
                    description     = excluded.description,
                    generated_type  = excluded.generated_type,
                    lifecycle_state = excluded.lifecycle_state,
                    body_json       = excluded.body_json,
                    created_at      = excluded.created_at,
                    updated_at      = excluded.updated_at;
                """,
                _to_row(concern, seq=seq),
            )
            # Tags are re-derived from the just-stored snapshot. We
            # drop and re-insert so the persisted tag set always
            # equals ``concern.generated_tags`` exactly — no leftover
            # rows from a previous upsert.
            cur.execute("DELETE FROM concern_tags WHERE concern_id = ?;", (concern.id,))
            tags = concern.generated_tags or []
            if tags:
                cur.executemany(
                    "INSERT OR IGNORE INTO concern_tags(concern_id, tag) VALUES (?, ?);",
                    [(concern.id, tag) for tag in tags],
                )

        # The defensive-copy contract: hand the caller a fresh model
        # object so they can't accidentally mutate stored state via
        # the return value.
        return concern.model_copy(deep=True)

    def get(self, concern_id: str) -> Concern | None:
        with self._lock:
            cur = self._conn.execute(
                "SELECT body_json FROM concerns WHERE id = ?;",
                (concern_id,),
            )
            row = cur.fetchone()
        return _from_row(row) if row is not None else None

    def delete(self, concern_id: str) -> None:
        # ``ON DELETE CASCADE`` on ``concern_tags`` cleans up the
        # tag rows as part of the same statement; idempotent because
        # DELETE on a missing row is a no-op in SQL.
        with self._lock, self._txn() as cur:
            cur.execute("DELETE FROM concerns WHERE id = ?;", (concern_id,))

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def list(
        self,
        *,
        kind: str | None = None,
        tag: str | None = None,
        lifecycle_state: str | None = None,
        limit: int | None = None,
    ) -> list[Concern]:
        if limit is not None and limit <= 0:
            return []

        clauses: list[str] = []
        params: list[Any] = []
        if kind is not None:
            clauses.append("c.kind = ?")
            params.append(kind)
        if lifecycle_state is not None:
            clauses.append("c.lifecycle_state = ?")
            params.append(lifecycle_state)
        # Tag filter joins against the side-table; INNER JOIN
        # naturally drops concerns with no matching tag.
        join = ""
        if tag is not None:
            join = "INNER JOIN concern_tags t ON t.concern_id = c.id AND t.tag = ?"
            params.insert(0, tag)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        sql = f"""
            SELECT c.body_json
            FROM concerns c
            {join}
            {where}
            ORDER BY c.seq ASC
        """
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)

        with self._lock:
            cur = self._conn.execute(sql, params)
            rows = cur.fetchall()
        return [_from_row(row) for row in rows]

    def search(self, query: str, *, limit: int = 20) -> list[Concern]:
        needle = query.strip().lower()
        if not needle:
            return []
        if limit <= 0:
            return []

        # Escape LIKE metacharacters (``%`` / ``_`` / ``\``) so a
        # query containing them matches as a literal substring —
        # i.e. the same semantics as ``MemoryConcernStore.search``,
        # which does a plain Python ``in``-test. Without this,
        # ``search("%")`` would match every row in sqlite but no
        # rows in memory, and the two backends would drift on a
        # surprisingly common input (Codex P2 on PR-13).
        like = f"%{_escape_like(needle)}%"
        sql = """
            SELECT body_json
            FROM concerns
            WHERE LOWER(name) LIKE ? ESCAPE '\\'
               OR LOWER(description) LIKE ? ESCAPE '\\'
            ORDER BY seq ASC
            LIMIT ?;
        """
        with self._lock:
            cur = self._conn.execute(sql, (like, like, limit))
            rows = cur.fetchall()
        return [_from_row(row) for row in rows]

    def iter_all(self) -> Iterable[Concern]:
        # Snapshot the rows under the lock so callers can iterate
        # lazily without holding it. Mirrors the memory backend's
        # behaviour: a long-running iteration won't block writers.
        with self._lock:
            cur = self._conn.execute("SELECT body_json FROM concerns ORDER BY seq ASC;")
            rows = cur.fetchall()
        for row in rows:
            yield _from_row(row)

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        with self._lock:
            cur = self._conn.execute("SELECT COUNT(*) AS n FROM concerns;")
            return int(cur.fetchone()["n"])

    def __contains__(self, concern_id: object) -> bool:
        if not isinstance(concern_id, str):
            return False
        with self._lock:
            cur = self._conn.execute(
                "SELECT 1 FROM concerns WHERE id = ? LIMIT 1;",
                (concern_id,),
            )
            return cur.fetchone() is not None

    def clear(self) -> None:
        """Drop every stored concern. Test/debug helper.

        Cascades to ``concern_tags`` via the foreign-key constraint
        — explicitly deleting tag rows would be a no-op but we do
        it anyway to make the intent obvious to a future reader.
        """
        with self._lock, self._txn() as cur:
            cur.execute("DELETE FROM concern_tags;")
            cur.execute("DELETE FROM concerns;")


__all__ = ["SqliteConcernStore"]
