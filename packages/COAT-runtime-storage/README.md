# COAT-runtime-storage

Persistence backends for `ConcernStore` and `DCNStore`. M0 ships only the
package skeleton — actual backends arrive at M1 (memory) and M3 (sqlite + jsonl).

```text
COAT_runtime_storage/
├── memory/    # default, zero-deps, M1
├── sqlite/    # single-process persistence, M3
├── postgres/  # service deployments, M8
├── jsonl/     # append-only log for replay/audit, M3
└── vector/    # optional: FAISS / LanceDB index, M2+
```
