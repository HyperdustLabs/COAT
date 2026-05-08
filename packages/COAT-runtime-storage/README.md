# COAT-runtime-storage

Persistence backends for `ConcernStore` and `DCNStore`. M0 shipped the
package skeleton; M1 added the in-memory backends; M3 is filling in the
single-process persistent ones (sqlite first, jsonl next).

```text
COAT_runtime_storage/
├── memory/    # default, zero-deps, M1
├── sqlite/    # single-process persistence, M3 (PR-13: ConcernStore landed)
├── postgres/  # service deployments, M8
├── jsonl/     # append-only log for replay/audit, M3
└── vector/    # optional: FAISS / LanceDB index, M2+
```

## SQLite backend (M3)

```python
from COAT_runtime_storage.sqlite import SqliteConcernStore

# In-memory (the default) — handy for tests:
store = SqliteConcernStore()

# On-disk; the parent directory is auto-created on first construction:
store = SqliteConcernStore("/var/lib/coat/concerns.db")

# Or as a context manager — closes the underlying connection on exit:
with SqliteConcernStore("/var/lib/coat/concerns.db") as store:
    store.upsert(my_concern)
```

The SQLite backend implements the same `ConcernStore` protocol as the
in-memory one (same defensive-copy semantics, same insertion-order
guarantee), so swapping it in is a one-line constructor change. The
full `Concern` envelope is round-tripped via `model_dump(mode="json")`
into a `body_json` column, with hot fields (`kind`, `name`,
`description`, `generated_type`, `lifecycle_state`) projected into
typed columns and `generated_tags` normalised into a `concern_tags`
side-table for fast tag filtering. No extra dependency — Python's
stdlib `sqlite3` is enough.
