# OpenCOAT Runtime — overview

> See [`design/v0.1-complete-design.md`](design/v0.1-complete-design.md) for
> the conceptual definition and [`design/v0.2-system-design.md`](design/v0.2-system-design.md)
> for the engineering layout.

```text
OpenCOAT Runtime
= SoC for Agent Thinking
+ Concern-first Runtime
+ AOP-style Weaving Mechanism
+ Deep Concern Network
```

## What it is

A general-purpose, host-agnostic cognitive runtime that organizes an LLM
agent's thinking with **Concerns** as the unit of reasoning, **AOP** as
the activation mechanism, and a **DCN (Deep Concern Network)** as the
long-term memory of those concerns.

Concretely, when the host agent reaches an observable point in its
pipeline (a *joinpoint*: receiving user input, before reasoning, before
a tool call, …), the runtime:

1. **Extracts** candidate concerns from the inputs.
2. **Builds / merges** them against the existing DCN.
3. **Matches** their pointcuts against the current joinpoint.
4. **Coordinates** a budget-aware activation (the *Concern Vector*).
5. **Resolves** conflicts, duplicates, escalations.
6. **Generates** advice (11 types: reasoning_guidance, tool_guard, …).
7. **Weaves** that advice back into the host's prompt / tool call /
   memory / output / verification slot.
8. **Verifies** the result and updates lifecycle state.
9. **Heartbeats** in the background to decay, merge, archive, evolve.

The runtime never decides *what* the agent should do. It decides *what
the agent should currently be paying attention to*.

## What it is not

- Not a prompt manager (it does not own prompts).
- Not a skill manager (it does not own tools).
- Not a planner (it does not produce plans).
- Not a domain framework (it does not encode trading / coding / research
  semantics — those are concerns the host generates).

## How to read the docs

Pick your entry point:

- *Just want the concepts?* → [`design/v0.1-complete-design.md`](design/v0.1-complete-design.md)
- *Want to embed the runtime?* → [`design/v0.2-system-design.md`](design/v0.2-system-design.md) §6
- *Want to write a host adapter?* → `05-plugins/host-adapter-spec.md` (M5)
- *Want to operate the daemon?* → `06-operations/daemon.md` (M4)
- *Want to follow milestones?* → `07-mvp/milestones.md`
