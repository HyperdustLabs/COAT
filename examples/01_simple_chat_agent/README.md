# 01 — Simple chat agent

The smallest end-to-end run of the COAT Runtime.

* In-process runtime, in-memory stores, deterministic stub LLM
* Hand-authored concerns (the M1 extractor is still a stub; M2 will replace this step with a real extraction call)
* One user input → matched concerns → woven injection → verified reply

This example lands as the M1 exit demo. It does not hit the network and
runs in ≈ 50 ms on a laptop.

## Layout

```text
examples/01_simple_chat_agent/
├── README.md          ← you are here
├── __init__.py        ← exports `SimpleChatAgent`, `TurnReport`, `seed_concerns`
├── agent.py           ← host-side glue around `COATRuntime`
├── concerns.py        ← three demo concerns (response req / verify rule / tool guard)
└── main.py            ← CLI entry point
```

## Run it

From the workspace root:

```bash
uv run python -m examples.01_simple_chat_agent.main
```

Or with your own prompts:

```bash
uv run python -m examples.01_simple_chat_agent.main \
  "Who invented COAT?" "Tell me how concerns are matched."
```

## What the demo proves

Every line of `SimpleChatAgent.handle` exercises a different M1 module:

| Step | Module |
| --- | --- |
| Build `JoinpointEvent` | `COAT_runtime_protocol.envelopes` |
| `runtime.on_joinpoint` | `loops.turn_loop.TurnLoop` |
| Candidate scan | `pointcut.matcher.PointcutMatcher` + 12 strategies |
| Rank / dedupe / budget / top-K | `coordinator.ConcernCoordinator` |
| Render advice | `advice.AdviceGenerator` + `templates` |
| Build injection | `weaving.ConcernWeaver` |
| DCN activation log | `MemoryDCNStore.log_activation` |
| Verify | `concern.verifier.ConcernVerifier` |

The wire-format `ConcernInjection` is the public contract — a real host
would consume it the same way the example does.

## Demo concerns

| id | kind | trigger | what it does |
| --- | --- | --- | --- |
| `c-concise` | `response_requirement` | keywords `?`, `explain`, `tell` | inserts a "≤ 3 sentences" directive at output level |
| `c-cite` | `verification_rule` | keywords `who`, `what`, `when`, `where`, `why`, `how` | post-checks the reply for `[N]` or `https://` |
| `c-no-pii` | `tool_guard` | keywords `email`, `phone`, `ssn`, `address` | blocks at output level (host must redact) |

You can swap them out by passing your own list to `SimpleChatAgent(concerns=[...])`.

## Sample output

The first prompt — *“Who invented the COAT runtime?”* — matches the *be
concise* keyword (`?`) and the *cite-sources* keyword (`who`). The
`no-pii` concern stays dormant. The reply embeds both directives and the
verifier passes the citation rule because the placeholder reply contains
`[1]`. Real hosts swap the placeholder for an LLM call once M2 lands.
