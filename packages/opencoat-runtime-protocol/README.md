# opencoat-runtime-protocol

Source-of-truth data contracts for the OpenCOAT Runtime.

This package owns:

- `opencoat_runtime_protocol/schemas/*.json` — JSON Schemas (Draft 2020-12) for every cross-process object
- `opencoat_runtime_protocol/openapi/runtime.yaml` — HTTP/JSON-RPC daemon API
- `opencoat_runtime_protocol/envelopes.py` — pydantic models that mirror the schemas

Schemas (one file per concept, mirrors v0.1 §6–§19):

| Schema | Concept |
| --- | --- |
| `concern.schema.json` | Concern (the unit) |
| `meta_concern.schema.json` | Meta Concern (Concern of Concern) |
| `joinpoint.schema.json` | Joinpoint event (8 levels) |
| `pointcut.schema.json` | Activation rule |
| `advice.schema.json` | Generated guidance (11 types) |
| `weaving.schema.json` | Weaving operation (11 ops × multiple targets) |
| `copr.schema.json` | Concern-Oriented Prompt Representation |
| `concern_vector.schema.json` | Sparse activation snapshot |
| `concern_injection.schema.json` | Output of weaving (host-consumable) |

Any change to a schema **must** bump `schema_version` and ship a migration note.
