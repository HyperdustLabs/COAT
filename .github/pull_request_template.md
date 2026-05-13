## Summary

What does this PR change, and why? Link related issues if any.

---

## Milestone

Which roadmap slice does this belong to? (See [`docs/design/v0.2-system-design.md`](../docs/design/v0.2-system-design.md) §12.)

- [ ] Not tied to a numbered milestone (docs-only / chore / CI)
- [ ] **M0** — Skeleton
- [ ] **M1** — In-proc happy path
- [ ] **M2** — Real LLM
- [ ] **M3** — Persistence (sqlite / jsonl replay)
- [ ] **M4** — Daemon + CLI + HTTP transport
- [ ] **M5** — OpenClaw plugin
- [ ] **M6** — Heartbeat + Meta workers
- [ ] **M7** — Second host (LangGraph / Hermes)
- [ ] **M8** — Postgres + K8s / Helm

---

## Type of change

- [ ] Bug fix (non-breaking)
- [ ] New feature / capability (backward compatible)
- [ ] Breaking change (wire format, public API, or default behaviour)
- [ ] Documentation only
- [ ] CI / tooling only

---

## Protocol & contracts

Skip if this PR does not touch schemas or public wire types.

- [ ] No changes under `packages/opencoat-runtime-protocol/opencoat_runtime_protocol/schemas/`
- [ ] **OR** I updated JSON Schemas and bumped `schema_version` where required
- [ ] **OR** I only adjusted comments / examples / OpenAPI without changing validation behaviour

If schemas changed, describe migration impact:

---

## Architecture decisions (ADR)

- [ ] No ADR impact
- [ ] **OR** I updated or added an ADR under [`docs/adr/`](../docs/adr/)
- [ ] **OR** I will follow up with an ADR in a separate PR (explain below)

---

## Verification

Local checks (same surface as CI):

```bash
uv sync --all-extras --dev
uv run ruff check . && uv run ruff format --check .
uv run python tools/schema_check.py
uv run pytest
```

- [ ] I ran the commands above (or equivalent) and they pass
- [ ] **OR** CI-only / docs-only — not applicable (explain)

---

## Packages / modules touched

Check any that apply:

- [ ] `opencoat-runtime-protocol` (PyPI package — schema / data contract)
- [ ] `opencoat-runtime` → `opencoat_runtime_core`
- [ ] `opencoat-runtime` → `opencoat_runtime_storage`
- [ ] `opencoat-runtime` → `opencoat_runtime_llm`
- [ ] `opencoat-runtime` → `opencoat_runtime_daemon`
- [ ] `opencoat-runtime` → `opencoat_runtime_cli`
- [ ] `opencoat-runtime-host` → `opencoat_runtime_host_sdk`
- [ ] `opencoat-runtime-host` → adapter (`openclaw` / `hermes` / `langgraph` / `autogen` / `crewai` / `custom`)
- [ ] Root workspace / CI / deploy / docs only

---

## Screenshots / examples

Optional: CLI output, diagram, or short transcript for behavioural changes.

---

## Notes for reviewers

Anything non-obvious: trade-offs, follow-ups, or areas you want extra scrutiny.
