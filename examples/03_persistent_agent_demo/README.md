# 03 — Persistent agent demo (M3 PR-16)

Single-process **sqlite** persistence for `ConcernStore` + `DCNStore`
(one shared database file) plus an optional **append-only JSONL**
session log compatible with `COATr replay`.

This example mirrors the turn shape of [`01_simple_chat_agent`](../01_simple_chat_agent/README.md)
(stub LLM, verifier, hand-authored concerns) so you can focus on the
storage wiring.

## Layout

```text
examples/03_persistent_agent_demo/
├── README.md       ← you are here
├── __init__.py
├── agent.py        # PersistentAgent + sqlite + SessionJsonlRecorder
├── concerns.py     # same three demo concerns as the M1 example
└── main.py         # CLI (live run + --replay)
```

## Run

From the repo root:

```bash
uv run python -m examples.03_persistent_agent_demo.main
```

Defaults write under `./.opencoat-persistent-demo/` (`state.db` +
`session.jsonl`). Override paths or disable JSONL:

```bash
uv run python -m examples.03_persistent_agent_demo.main \
  --state-db /tmp/opencoat/state.db \
  --session-log /tmp/opencoat/session.jsonl \
  "What is concern weaving?"

uv run python -m examples.03_persistent_agent_demo.main --no-jsonl
```

## Replay

After a run with JSONL enabled:

```bash
COATr replay ./.opencoat-persistent-demo/session.jsonl
```

Or via this package’s CLI (no daemon):

```bash
uv run python -m examples.03_persistent_agent_demo.main \
  --replay ./.opencoat-persistent-demo/session.jsonl
```

## Seeding semantics

`PersistentAgent(..., concerns=None)` loads `seed_concerns()` **only if**
the sqlite store is empty. Pointing at an existing `state.db` therefore
resumes the same concern rows (and lifecycle metrics) across runs — the
main thing this demo is meant to prove.

## Related code

| Piece | Location |
| --- | --- |
| Sqlite stores | `opencoat_runtime_storage.sqlite` |
| JSONL recorder + replay | `opencoat_runtime_storage.jsonl` |
| ADR | [`docs/adr/0007-jsonl-replay-as-debug-source.md`](../../docs/adr/0007-jsonl-replay-as-debug-source.md) |
