# Safety rules — what the host agent must respect

These rules govern how the **host agent** must react when OpenCOAT
weaves an injection into its joinpoint stream. They are the contract
between the runtime and any host adapter; violating them is what
`MetaConcern` will eventually flag (M6).

## Rule 1 — `TOOL_GUARD` blocks are non-negotiable

When OpenCOAT returns a `WeavingOperation.BLOCK` for a `TOOL_GUARD`
advice on `before_tool_call`, the host **must** abort that tool call
and surface the advice's `content` to the model as the tool's error
result. The host **must not** retry the same call with cosmetic edits
to dodge the keyword match.

The OpenClaw `tool_guard` interpreter (M5 PR #30) already enforces
this; the same contract applies to every other host adapter.

## Rule 2 — `MEMORY_WRITE_GUARD` annotations stay attached

When advice with type `MEMORY_WRITE_GUARD` and mode `ANNOTATE`
returns a `memory_write.policy_note`, the host **must** persist that
note alongside the memory record. Stripping or rewriting the note in
flight breaks the DCN's audit trail (M5 PR #31's `OpenClawMemoryBridge`
mirrors the annotated write into the DCN).

If the host's storage layer cannot accept a free-form note, store the
note JSON as a sibling row keyed on the same write id rather than
silently dropping it.

## Rule 3 — `RESPONSE_REQUIREMENT` is checked, not assumed

When advice with type `RESPONSE_REQUIREMENT` is woven into the prompt
(e.g. `demo-prompt-prefix`), the host's verifier loop **should** check
the actual response satisfies the requirement before emitting it. The
runtime's `concern_verifier` runs this check when it has access to the
response, but in some host topologies the host is the only one holding
the final string — in that case the host owns the check.

If the response fails the requirement, the host should re-prompt with
the verifier's verdict appended, not silently emit the bad response.

## Rule 4 — Concerns flow through `concern.upsert`, never edited in place

Concerns are immutable from the host's point of view. To change a
concern, the host **must** call `concern.upsert` with the new payload —
the runtime handles version bumps, lifecycle transitions, and DCN
edge updates. Editing the on-disk JSON or mutating the in-memory
`Concern` object bypasses lifecycle accounting and will diverge from
what the daemon believes.

## Rule 5 — `lifecycle_state` is owned by the runtime

Hosts read `concern.lifecycle_state` (`active` / `pending` / `archived`)
but **must not** set it directly. State transitions are driven by the
M2 `ConcernLifecycleManager` (and M6 workers, when those land); a host
that writes the field directly will be overwritten on the next worker
tick.

## Rule 6 — Joinpoint emission is the host's responsibility, end to end

The host adapter **must** emit a joinpoint for **every** event in its
subscription list, even when the runtime returned no injections last
time. The runtime relies on the gap-free joinpoint stream to compute
decay and conflict scores; selectively dropping "boring" events
biases the DCN.

Use `opencoat dcn activation-log` to confirm the joinpoint cadence
matches the host's actual event rate.

## Rule 7 — PID files are advisory, sockets are authoritative

When `opencoat runtime status` and `runtime up` disagree, trust the
HTTP `health.ping` over the PID file. A stale PID file (e.g. after a
`SIGKILL`) is harmless once the new daemon binds the listener;
deleting the stale file is safe before `runtime up`.

## Rule 8 — AI assistants must not collect LLM API keys in chat

Coding agents following this skill **must not** ask the human to paste
`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, Azure secrets, or any bearer token
into the chat transcript. Keys belong in the operator's **local shell**
(`opencoat configure llm`, `~/.opencoat/opencoat.env` — the daemon merges
allow-listed LLM keys from that file at startup — shell profile, or
inline YAML via the same wizard) — never in a shared agent thread.

## When in doubt

Run `opencoat inspect joinpoints` and `opencoat inspect pointcuts` —
both work without a daemon, both reflect the exact catalogs
`opencoat_runtime_core` is using right now, and both are the
authoritative source for "what does this name mean?"
