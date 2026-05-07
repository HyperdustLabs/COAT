# ADR 0001 — Concern as the first-class unit

## Status

Accepted (v0.1).

## Context

Most agent frameworks structure their reasoning around prompts, tools, or
"skills". Each of those abstractions is convenient locally but breaks at
scale: prompts grow into walls of rules; tools encode behaviour but not
intent; skills encode capabilities but not why those capabilities matter.

We want a single durable unit that survives across turns, can be
inspected, can carry policy, and can compose with other units.

## Decision

The COAT Runtime treats **Concern** as the only first-class data
structure. A Concern is what the agent is currently paying attention to
— it can be a long-lived value (`"don't fabricate facts"`), a short-lived
goal (`"summarize this paper"`), or a meta concern about the runtime
itself (`"keep injection budget under 800 tokens"`).

Everything else (joinpoint events, pointcuts, advice, weaving, DCN
relations) exists in service of producing, activating, or verifying a
Concern.

## Consequences

- The runtime never enumerates business types. The only runtime-level
  classification is `kind: concern | meta_concern`. Domain semantics
  live in `generated_type` / `generated_tags`, supplied by the LLM.
- Concerns are persistable, activatable, injectable, verifiable,
  evolvable, relatable — see v0.1 §3.1.
- Every other module (extractor, separator, builder, coordinator,
  resolver, weaver, verifier, lifecycle manager) is named after the
  operation it performs *on a Concern*.
