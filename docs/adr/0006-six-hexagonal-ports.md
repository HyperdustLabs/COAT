# ADR 0006 — Hexagonal ports + adapters

## Status

Accepted (v0.2).

## Context

Storage, LLM, embedder, host adapter, matcher, advice plugin, and
observer are the seams where the runtime meets the outside world. We
want each one to be a plugin, not a hard dependency.

## Decision

Adopt ports & adapters (hexagonal architecture). Each port lives in
`COAT_runtime_core/ports/` as a `typing.Protocol` (runtime_checkable).
Concrete adapters live in their own packages
(`COAT-runtime-storage`, `COAT-runtime-llm`, `COAT-runtime-host-plugins/*`).

Current ports:

- `ConcernStore` — CRUD + search over concerns
- `DCNStore` — graph + activation history
- `LLMClient` — complete / chat / structured / score
- `Embedder` — embedding vectors
- `HostAdapter` — host events ↔ joinpoints
- `MatcherPlugin` — alternative pointcut matchers
- `AdvicePlugin` — alternative advice generators
- `Observer` — metrics / spans / structured logs

## Consequences

- The core has zero runtime dependencies on external services.
- Tests use trivial in-memory adapters; CI runs without network.
- Adding a new backend never requires touching the core.
