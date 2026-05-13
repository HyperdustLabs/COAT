# 02 — Coding agent demo

A coding agent driven by a **real** LLM (or the deterministic stub
when no creds are configured). The M2 exit demo: every M2 module —
real provider clients, the concern extractor, and the lifecycle
manager — wired into one host you can read top to bottom.

* In-process runtime, in-memory stores
* Provider auto-detected from the environment (OpenAI / Anthropic /
  Azure / stub) — see `llm.py`
* Hand-authored coding-policy concerns + an equivalent natural-
  language `GOVERNANCE_DOC` for `ConcernExtractor` to chew on
* `ConcernLifecycleManager.reinforce()` called for every concern
  that fires, demonstrating the M2 PR-11 lifecycle integration

CI runs without any provider keys set, so the smoke tests go through
the stub deterministically. Set one of `OPENAI_API_KEY`,
`ANTHROPIC_API_KEY`, or `AZURE_OPENAI_ENDPOINT` (+ deployment) to
flip into real-provider mode without touching agent code.

## Layout

```text
examples/02_coding_agent_demo/
├── README.md          ← you are here
├── __init__.py        ← exports `CodingAgent`, `TurnReport`, `seed_concerns`, `select_llm`
├── agent.py           ← host glue around `OpenCOATRuntime` + LLM chat + lifecycle
├── concerns.py        ← five hand-authored concerns + `GOVERNANCE_DOC`
├── llm.py             ← env-driven provider selection with stub fallback
└── main.py            ← CLI entry point
```

## Run it

From the workspace root:

```bash
uv run python -m examples.02_coding_agent_demo.main
```

With your own prompts:

```bash
uv run python -m examples.02_coding_agent_demo.main \
  "How do I read JSON from a file?" \
  "Write a recursive Fibonacci function."
```

Force a provider (the default ladder is in `llm.py`):

```bash
OPENCOAT_DEMO_PROVIDER=stub      uv run python -m examples.02_coding_agent_demo.main
OPENCOAT_DEMO_PROVIDER=openai    uv run python -m examples.02_coding_agent_demo.main
OPENCOAT_DEMO_PROVIDER=anthropic uv run python -m examples.02_coding_agent_demo.main
OPENCOAT_DEMO_PROVIDER=azure     uv run python -m examples.02_coding_agent_demo.main
```

Override the model / deployment (the defaults are conservative and
cheap):

```bash
OPENCOAT_DEMO_OPENAI_MODEL=gpt-4o-mini      \
OPENCOAT_DEMO_ANTHROPIC_MODEL=claude-3-5-haiku-latest \
OPENCOAT_DEMO_AZURE_DEPLOYMENT=my-deployment \
  uv run python -m examples.02_coding_agent_demo.main
```

## What the demo proves

| Step | Module | M2 PR |
| --- | --- | --- |
| Provider selection | `examples.02_coding_agent_demo.llm.select_llm` | PR-7..PR-9 |
| Build `JoinpointEvent` | `opencoat_runtime_protocol.envelopes` | PR-1 |
| `runtime.on_joinpoint` | `loops.turn_loop.TurnLoop` | PR-5 |
| Match · coordinate · weave | the M1 stack | PR-2..PR-6 |
| LLM call | `OpenAILLMClient` / `AnthropicLLMClient` / `AzureOpenAILLMClient` | PR-7..PR-9 |
| Verify | `concern.verifier.ConcernVerifier` | PR-3 |
| Reinforce active concerns | `concern.lifecycle.ConcernLifecycleManager` | **PR-11** |

`ConcernExtractor` (PR-10) isn't called per-turn in the demo —
governance docs are imported at boot time, not on every user
request — but the bundled `GOVERNANCE_DOC` is shaped so a single
`extractor.extract_from_governance_doc(GOVERNANCE_DOC)` call
produces a roughly-equivalent set to `seed_concerns()`. Running it
yourself takes one snippet:

```python
from opencoat_runtime_core.concern.extractor import ConcernExtractor
from examples.02_coding_agent_demo import GOVERNANCE_DOC, select_llm

llm, _ = select_llm()  # needs a real provider; stub returns empty {}
extractor = ConcernExtractor(llm=llm)
result = extractor.extract_from_governance_doc(GOVERNANCE_DOC)
for c in result.concerns:
    print(c.id, c.name)
```

## Demo concerns

| id | kind | trigger keywords | what it does |
| --- | --- | --- | --- |
| `c-no-eval` | `tool_guard` | `eval`, `exec`, `dynamic`, `metaprogram` | blocks `eval()` / `exec()` in code blocks |
| `c-type-hints` | `response_requirement` | `def `, `function`, `method`, `implement`, `write a` | enforces parameter + return type hints |
| `c-cite-docs` | `verification_rule` | `how do i`, `syntax`, `what does`, `stdlib`, `module` | post-checks the reply for a doc URL or `[N]` marker |
| `c-no-malware` | `tool_guard` | `malware`, `exploit`, `keylogger`, `ransomware`, `rootkit`, `steal`, `exfiltrate` | refuses harmful-code requests |
| `c-prefer-stdlib` | `reasoning_guidance` | `library`, `package`, `pip`, `dependency`, `import` | nudges toward stdlib over third-party deps |

Override or drop them via `CodingAgent(concerns=[...])`; pass `[]` to
start with an empty store.

## Sample output (stub)

```text
LLM: stub

── Turn 1 ────────────────────────────────────────────────────────────
user: How do I parse a JSON string in Python?
active concerns (3): c-cite-docs, c-prefer-stdlib, c-type-hints
injections:
  • [verification_rule] target=response.citations mode=verify level=verification
      The reply MUST contain at least one URL pointing to ...
  • [reasoning_guidance] target=reasoning.preferences mode=insert level=message
      Default to the Python standard library. ...
  • [response_requirement] target=response.code_style mode=insert level=output
      Every Python function in the answer must include parameter ...
response:
  (stub) The OpenCOAT runtime is wired up correctly, ... See https://docs.python.org/3/ for the language reference [1].
verifications:
  ✓ c-cite-docs: score=1.00 notes=...
reinforced: c-cite-docs, c-prefer-stdlib, c-type-hints
```

A real provider returns a real coding answer in the `response:` slot —
everything else (concerns, injections, verifications, reinforcements)
stays the same.
