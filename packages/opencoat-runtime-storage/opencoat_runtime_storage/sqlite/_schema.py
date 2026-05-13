"""DDL constants for the SQLite storage backend.

Kept in a dedicated module so callers (tooling, tests, future
``alembic``-style migrations) can introspect the canonical schema
without importing the runtime classes.

Two parallel schemas live here, one per store:

* ``bootstrap_sql()`` — :class:`SqliteConcernStore`. ``concerns`` +
  ``concern_tags`` side-table + the shared ``meta`` table.
* ``bootstrap_dcn_sql()`` — :class:`SqliteDCNStore`. ``dcn_nodes`` +
  ``dcn_edges`` (composite PK ``(src, dst, relation_type)`` so
  multiple relations between the same pair coexist) +
  ``dcn_activations`` (append-only event log) + the shared ``meta``
  table.

Each store's bootstrap is independent (no cross-table FKs) and idem-
potent — a host can point both stores at the same SQLite file and
have each one CREATE-IF-NOT-EXISTS its own tables. Per-store schema
versions live as separate keys in the shared ``meta`` table so
neither one stomps the other:

* ``schema_version``     — concern-store tables
* ``dcn_schema_version`` — dcn-store tables

``ON DELETE CASCADE`` is enforced at every join boundary so removing
a parent row (concern, dcn-node) takes its dependents (tags, edges,
activations) with it. This requires ``PRAGMA foreign_keys = ON`` at
connection open time, which both store implementations do.
"""

from __future__ import annotations

# Bumped only on backwards-incompatible schema changes. Stored in the
# ``meta`` table so a future migration runner can read it without
# inspecting the table definitions directly.
SCHEMA_VERSION: int = 1
DCN_SCHEMA_VERSION: int = 1


_BOOTSTRAP_SQL: str = """
CREATE TABLE IF NOT EXISTS concerns (
    id               TEXT    PRIMARY KEY,
    seq              INTEGER NOT NULL UNIQUE,
    kind             TEXT    NOT NULL,
    name             TEXT    NOT NULL,
    description      TEXT    NOT NULL DEFAULT '',
    generated_type   TEXT,
    lifecycle_state  TEXT    NOT NULL,
    body_json        TEXT    NOT NULL,
    created_at       TEXT,
    updated_at       TEXT
);

CREATE INDEX IF NOT EXISTS ix_concerns_kind            ON concerns(kind);
CREATE INDEX IF NOT EXISTS ix_concerns_lifecycle_state ON concerns(lifecycle_state);
CREATE INDEX IF NOT EXISTS ix_concerns_generated_type  ON concerns(generated_type);
CREATE INDEX IF NOT EXISTS ix_concerns_seq             ON concerns(seq);

CREATE TABLE IF NOT EXISTS concern_tags (
    concern_id TEXT NOT NULL,
    tag        TEXT NOT NULL,
    PRIMARY KEY (concern_id, tag),
    FOREIGN KEY (concern_id) REFERENCES concerns(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_concern_tags_tag ON concern_tags(tag);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


_BOOTSTRAP_DCN_SQL: str = """
CREATE TABLE IF NOT EXISTS dcn_nodes (
    id              TEXT    PRIMARY KEY,
    lifecycle_state TEXT    NOT NULL,
    body_json       TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_dcn_nodes_lifecycle_state ON dcn_nodes(lifecycle_state);

-- Composite PK on (src, dst, relation_type) so multiple distinct
-- relations between the same pair coexist (e.g. ``activates`` and
-- ``constrains``).  ``seq`` is a monotone insertion-order counter
-- used by ``neighbors()`` to mirror MemoryDCNStore's dict-iteration
-- ordering.  Both endpoints CASCADE-delete so removing a node
-- nukes its dangling edges automatically.
CREATE TABLE IF NOT EXISTS dcn_edges (
    src           TEXT    NOT NULL,
    dst           TEXT    NOT NULL,
    relation_type TEXT    NOT NULL,
    weight        REAL    NOT NULL,
    seq           INTEGER NOT NULL,
    PRIMARY KEY (src, dst, relation_type),
    FOREIGN KEY (src) REFERENCES dcn_nodes(id) ON DELETE CASCADE,
    FOREIGN KEY (dst) REFERENCES dcn_nodes(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_dcn_edges_src ON dcn_edges(src);
CREATE INDEX IF NOT EXISTS ix_dcn_edges_dst ON dcn_edges(dst);
CREATE INDEX IF NOT EXISTS ix_dcn_edges_seq ON dcn_edges(seq);

-- Activations are an append-only event log; ``seq`` doubles as the
-- primary key and as the chronological order used by
-- ``activation_log(limit=N)`` (returns the last ``N`` records in
-- chronological order, not reverse).
CREATE TABLE IF NOT EXISTS dcn_activations (
    seq          INTEGER PRIMARY KEY AUTOINCREMENT,
    concern_id   TEXT    NOT NULL,
    joinpoint_id TEXT    NOT NULL,
    score        REAL    NOT NULL,
    ts           TEXT    NOT NULL,
    FOREIGN KEY (concern_id) REFERENCES dcn_nodes(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_dcn_activations_concern ON dcn_activations(concern_id);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def bootstrap_sql() -> str:
    """Return the idempotent ConcernStore CREATE-TABLE bundle.

    Kept as a function (rather than a bare module-level constant) so
    callers can pass the string straight into ``executescript`` /
    ``conn.executescript`` without copying.
    """
    return _BOOTSTRAP_SQL


def bootstrap_dcn_sql() -> str:
    """Return the idempotent DCNStore CREATE-TABLE bundle.

    Independent of :func:`bootstrap_sql`; both can be applied to the
    same database (the shared ``meta`` table is ``IF NOT EXISTS``).
    """
    return _BOOTSTRAP_DCN_SQL


__all__ = [
    "DCN_SCHEMA_VERSION",
    "SCHEMA_VERSION",
    "bootstrap_dcn_sql",
    "bootstrap_sql",
]
