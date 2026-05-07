# Milestones

Source: [`design/v0.2-system-design.md`](../design/v0.2-system-design.md) §12.

| Milestone | Scope | Exit criteria | Status |
| --- | --- | --- | --- |
| **M0 — Skeleton** | Monorepo skeleton, JSON schemas, empty core skeleton, CI | `pytest` passes empty tests; schema validation passes | ✅ in this commit |
| **M1 — In-proc happy path** | All 17 core modules with stub implementations + memory backend + stub LLM + `01_simple_chat_agent` | Single turn walks `extract → match → advise → weave → verify → lifecycle` | pending |
| **M2 — Real LLM** | OpenAI / Anthropic clients; `extractor` / `advice` / `verifier` use real LLMs | `02_coding_agent_demo` passes with a real LLM | pending |
| **M3 — Persistence** | sqlite backend + restart recovery + jsonl replay | DCN survives restart; `COATr replay` reproduces a turn | pending |
| **M4 — Daemon + CLI** | Daemon HTTP/JSON-RPC + `COATr` CLI + host-sdk HTTP transport | Host calls daemon over socket and completes a turn | pending |
| **M5 — OpenClaw plugin** | Full `host-plugins/openclaw` adapter | `04_openclaw_with_runtime` runs end-to-end | pending |
| **M6 — Heartbeat + Meta** | Decay / conflict / merge / archive / meta-review workers | 24h soak: DCN converges, token budget stable | pending |
| **M7 — Second host** | LangGraph (or Hermes) adapter; multi-host shared DCN | Two hosts share one DCN without conflict | pending |
| **M8 — Postgres + K8s** | Postgres backend + helm chart | 7-day stability on a K8s cluster | pending |
