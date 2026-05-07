# ADR 0004 — COPR as the prompt-side intermediate representation

## Status

Accepted (v0.1).

## Context

Pointcuts must be able to match at sub-message granularity (a span, a
single token, a structure field). Plain string prompts make that
impossible without each pointcut re-implementing tokenisation.

## Decision

Introduce **COPR (Concern-Oriented Prompt Representation)** — a
structured prompt tree (a "Thought DOM") with messages → sections →
spans → tokens. The pointcut matcher always operates on COPR, never on
raw strings.

## Consequences

- The runtime owns a parser, a span segmenter, and a renderer.
- Hosts that already produce structured messages can hand them over
  directly; hosts that produce raw strings get default segmentation.
- Token-level joinpoints are restricted to *visible* token streams
  (input prompts, structured arguments, output drafts) — they never
  expose hidden model reasoning.
