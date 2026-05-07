# ADR 0005 — Runtime / Daemon process boundary

## Status

Accepted (v0.2).

## Context

We want the runtime to be embeddable (in-proc library) **and** runnable
as a long-lived service shared by multiple host processes.

## Decision

Split the codebase into a **core library** (`COAT-runtime-core`,
no I/O assumptions, hexagonal ports) and a **daemon process**
(`COAT-runtime-daemon`) that composes the core with concrete adapters
and exposes:

- in-proc API (no transport)
- Unix domain socket
- HTTP / JSON-RPC
- (optional, post-M5) gRPC

Same library, three deployment topologies (in-proc, sidecar,
daemon-server). Hosts pick at connection time.

## Consequences

- Core remains testable without any servers running.
- Multiple hosts can share a daemon (and a DCN), enabling
  cross-session learning later.
- The daemon owns scheduling, IPC, observability — those concerns
  never leak into the core.
