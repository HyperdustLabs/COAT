# ADR 0008 — Meta Concern as runtime governance

## Status

Accepted (v0.1, refined v0.2).

## Context

Some concerns are about other concerns: *"don't extract concerns from
unverified tool output"*, *"merge duplicates aggressively"*, *"keep
injection budget under 800 tokens"*. We want a principled place for
these without enumerating "safety_concern", "format_concern", … as
runtime types.

## Decision

`Meta Concern` is a kind of Concern (`kind: meta_concern`) plus a
required `governance_capability` discriminator chosen from a closed
set of 8 runtime governance capabilities:

1. extraction_control
2. separation_control
3. activation_control
4. conflict_resolution
5. verification_control
6. lifecycle_control
7. budget_control
8. evolution_control

The runtime exposes one module per capability under
`COAT_runtime_core/meta/`. Meta Concerns drive those modules — they
don't bypass them.

## Consequences

- Domain semantics still flow through `generated_type` / `generated_tags`,
  but anything *about the runtime itself* is structurally distinguished.
- Each governance module can be enabled / disabled / replaced via the
  meta plugin point.
- We don't need to add new "concern types" as the system evolves; we
  add new Meta Concern instances or new governance capabilities.
