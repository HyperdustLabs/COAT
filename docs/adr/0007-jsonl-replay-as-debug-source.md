# ADR 0007 — JSONL replay as a debug primitive

## Status

Accepted (v0.2).

## Context

Debugging concern activation across many turns is essentially
impossible without deterministic replay. We want every joinpoint
(input) and every injection (output) recorded so we can re-drive a turn
offline.

## Decision

The JSONL backend is a first-class storage option. It writes one record
per joinpoint and one per injection, in append-only files keyed by
session. `COATr replay session.jsonl` re-feeds the joinpoints into a
fresh runtime and diffs the injections.

## Consequences

- Replay is part of the test surface, not an afterthought.
- Schema versioning matters: every change to the wire format bumps
  `schema_version` so replay can detect mismatches.
- This is also our audit trail: with the JSONL log we can answer "why
  was this concern activated for that turn?"
