"""DDL constants for the SQLite storage backend.

Kept in a dedicated module so callers (tooling, tests, future
``alembic``-style migrations) can introspect the canonical schema
without importing the runtime classes.

Schema layout
-------------

The ``concerns`` table stores one row per :class:`Concern`. The full
pydantic dump lives in ``body_json`` (the source of truth for
round-trip fidelity); a fixed set of *hot* fields is projected into
typed columns so filters / searches can use proper SQL predicates
and indexes.

The ``concern_tags`` side-table stores one row per ``(concern_id,
tag)`` pair so ``list(tag=...)`` is a JOIN — exact, not substring
— and so re-tagging an existing concern (drop + insert) is a
single short transaction.

Both tables use ``ON DELETE CASCADE`` to keep tag rows in sync
with concern deletions, with ``PRAGMA foreign_keys = ON`` enforced
at connection open time.
"""

from __future__ import annotations

# Bumped only on backwards-incompatible schema changes. Stored in the
# ``meta`` table so a future migration runner can read it without
# inspecting the table definitions directly.
SCHEMA_VERSION: int = 1


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


def bootstrap_sql() -> str:
    """Return the idempotent CREATE-TABLE bundle.

    Kept as a function (rather than a bare module-level constant) so
    callers can pass the string straight into ``executescript`` /
    ``conn.executescript`` without copying.
    """
    return _BOOTSTRAP_SQL


__all__ = ["SCHEMA_VERSION", "bootstrap_sql"]
