# MVP scope

What MVP **does**:

- Concern data model (incl. Meta Concerns)
- Concern Store (in-memory, sqlite)
- Joinpoint model (8 levels, stable name catalog)
- COPR (basic)
- Pointcut matcher (12 strategies)
- Concern Coordinator + Resolver (top-K, budget, conflicts)
- Advice Generator (11 types) + Weaver (11 ops × 8 levels)
- Concern Verifier
- Concern Lifecycle Manager
- Host Adapter (OpenClaw first, others next)
- Three runtime loops (turn / event / heartbeat)
- Daemon (HTTP/JSON-RPC + Unix socket)

The MVP target flow:

```text
input
 → concern extraction
 → joinpoint / pointcut matching
 → concern activation
 → advice generation
 → weaving
 → host response
 → concern verification
 → concern update
```
