# opencoat-runtime-storage

Persistence backends for `ConcernStore` and `DCNStore`. M0 shipped the
package skeleton; M1 added the in-memory backends; M3 is filling in the
single-process persistent ones (sqlite first, jsonl next).

```text
opencoat_runtime_storage/
├── memory/    # default, zero-deps, M1
├── sqlite/    # single-process persistence, M3 (PR-13: ConcernStore, PR-14: DCNStore)
├── postgres/  # service deployments, M8
├── jsonl/     # append-only session log + replay (M3 PR-15)
└── vector/    # optional: FAISS / LanceDB index, M2+
```

## SQLite backends (M3)

```python
from opencoat_runtime_protocol import ConcernRelationType
from opencoat_runtime_storage.sqlite import SqliteConcernStore, SqliteDCNStore

# In-memory (the default) — handy for tests:
concerns = SqliteConcernStore()
dcn = SqliteDCNStore()

# On-disk — parent directories are auto-created on first construction.
# Both stores can safely share the same SQLite file (each bootstraps
# its own tables and writes a distinct ``meta`` schema-version key):
concerns = SqliteConcernStore("/var/lib/opencoat/state.db")
dcn      = SqliteDCNStore("/var/lib/opencoat/state.db")

# Or as context managers — close the underlying connection on exit:
with SqliteConcernStore("/var/lib/opencoat/state.db") as cs, \
     SqliteDCNStore("/var/lib/opencoat/state.db") as ds:
    cs.upsert(my_concern)
    ds.add_node(my_concern)
    ds.add_edge("a", "b", ConcernRelationType.ACTIVATES, weight=0.7)
```

Both implement the same `ConcernStore` / `DCNStore` protocols as the
in-memory backends — same defensive-copy semantics, same insertion-
order guarantees, same `merge` / `archive` behaviour — so swapping is
a one-line constructor change. The full envelope is round-tripped via
`model_dump(mode="json")` into a `body_json` column (the source of
truth); hot fields are projected into typed columns for fast filter /
search; tags and edges live in side-tables with `ON DELETE CASCADE`
foreign keys so node removal cleans up dependents automatically. No
extra dependency — Python's stdlib `sqlite3` is enough.

## JSONL session log (M3)

ADR [0007](../docs/adr/0007-jsonl-replay-as-debug-source.md): one `joinpoint`
line plus one `injection` line per turn, optional `session` header with
concern seeds for deterministic replay.

```python
from opencoat_runtime_storage.jsonl import SessionJsonlRecorder, replay_session_file

with SessionJsonlRecorder("session.jsonl", session_id="sess-1") as rec:
    rec.write_session_header(concerns=my_concerns)
    inj = runtime.on_joinpoint(jp)
    rec.record_turn(jp, inj)

assert replay_session_file("session.jsonl").ok
```

CLI (requires `opencoat-runtime-cli`):

```bash
COATr replay session.jsonl
```
