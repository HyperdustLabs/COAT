"""SQLite storage backends — M3.

The schema lives next door in :mod:`._schema`; the live store
classes are re-exported here for the canonical
``from COAT_runtime_storage.sqlite import SqliteConcernStore``
import path.

The SQLite backends require no extra dependency — Python's stdlib
ships :mod:`sqlite3`. Hosts that want WAL mode benefit from a
modern SQLite library, but the bootstrap falls back gracefully to
the default journal mode on platforms where WAL isn't allowed.
"""

from ._schema import SCHEMA_VERSION, bootstrap_sql
from .concern_store import SqliteConcernStore

__all__ = [
    "SCHEMA_VERSION",
    "SqliteConcernStore",
    "bootstrap_sql",
]
