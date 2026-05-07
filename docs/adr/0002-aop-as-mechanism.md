# ADR 0002 — AOP as the activation mechanism

## Status

Accepted (v0.1).

## Context

We need a runtime-time mechanism that decides *when* a concern should
influence the agent's thinking. The classical AOP triple
(joinpoint / pointcut / advice / weaving) is a near-perfect fit: it
already separates *where things happen*, *which events to react to*,
*what to inject*, and *how to inject it*.

## Decision

Adopt AOP as the runtime-time mechanism, but apply it to *agent
thinking* rather than *program execution*. The terminology stays the
same (joinpoint / pointcut / advice / weaving) but the substrate is the
agent's thought DOM (COPR), not Java bytecode.

We deliberately do **not** call the unit `Aspect`. AOP's *Aspect* is a
specifically *cross-cutting concern*; the COAT Runtime has both
cross-cutting and non-cross-cutting concerns, so the broader name
"Concern" wins. `Aspect ⊂ Concern`.

## Consequences

- 8 joinpoint levels (runtime / lifecycle / message / prompt-section /
  span / token / structure-field / thought-unit).
- 12 pointcut strategies.
- 11 advice types × 11 weaving operations × 8 weaving levels.
- The runtime stays generic: any host that can map its own events into
  the joinpoint catalog can use it.
