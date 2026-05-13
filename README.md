<p align="center">
  <img src="docs/moss-coat.png" alt="OpenCOAT Runtime logo" width="300" />
</p>

<h1 align="center">OpenCOAT</h1>

<p align="center">
  <strong>Open Concern-Oriented Agent Thinking Runtime</strong><br />
  a general-purpose, Concern-first cognitive runtime for LLM agents.
</p>

---

> OpenCOAT Runtime applies *Separation of Concerns* to **agent thinking** instead of program code,
> using `joinpoint / pointcut / advice / weaving` to organize, modulate, verify and evolve
> the way Host Agents reason, plan, call tools, write memory, and respond.

```text
OpenCOAT Runtime
= Concern-first Runtime
+ AOP-style Thinking Mechanism
+ Deep Concern Network
```

This repository is the reference implementation. It is `host-agnostic` — the runtime core does not
depend on any specific agent framework. Hosts (OpenClaw, Hermes, LangGraph, AutoGen, CrewAI, custom)
plug in via adapters.

---

## Status

Pre-alpha. We are working through the milestones defined in
[`docs/design/v0.2-system-design.md`](docs/design/v0.2-system-design.md) §12.

| Milestone | Scope | Status |
| --- | --- | --- |
| **M0** | Monorepo skeleton, JSON schemas, empty core skeleton, CI | ✅ complete |
| **M1** | In-proc happy path (memory + stub-llm + `01_simple_chat_agent`) | ✅ complete |
| **M2** | Real LLM (OpenAI / Anthropic / Azure) + extractor + lifecycle | ✅ complete — `OpenAILLMClient` ([PR-7 / #7](https://github.com/HyperdustLabs/OpenCOAT/pull/7)), `AnthropicLLMClient` ([PR-8 / #9](https://github.com/HyperdustLabs/OpenCOAT/pull/9)), `AzureOpenAILLMClient` ([PR-9 / #11](https://github.com/HyperdustLabs/OpenCOAT/pull/11)), `ConcernExtractor` ([PR-10 / #12](https://github.com/HyperdustLabs/OpenCOAT/pull/12)), `ConcernLifecycleManager` ([PR-11 / #13](https://github.com/HyperdustLabs/OpenCOAT/pull/13)), `examples/02_coding_agent_demo` ([PR-12 / #14](https://github.com/HyperdustLabs/OpenCOAT/pull/14)) |
| **M3** | Persistence (sqlite + jsonl replay) | ✅ complete — `SqliteConcernStore` ([PR-13 / #15](https://github.com/HyperdustLabs/OpenCOAT/pull/15)), `SqliteDCNStore` ([PR-14 / #16](https://github.com/HyperdustLabs/OpenCOAT/pull/16)), JSONL replay ([PR-15 / #18](https://github.com/HyperdustLabs/OpenCOAT/pull/18)), `examples/03_persistent_agent_demo` ([PR-16 / #20](https://github.com/HyperdustLabs/OpenCOAT/pull/20)) |
| **M4** | Daemon + CLI + HTTP/JSON-RPC | ✅ complete — `build_runtime` ([PR-17 / #21](https://github.com/HyperdustLabs/OpenCOAT/pull/21)), in-proc JSON-RPC ([PR-18 / #22](https://github.com/HyperdustLabs/OpenCOAT/pull/22)), stdlib HTTP JSON-RPC ([PR-19 / #23](https://github.com/HyperdustLabs/OpenCOAT/pull/23)), daemon lifecycle ([PR-20 / #24](https://github.com/HyperdustLabs/OpenCOAT/pull/24)), `opencoat runtime up\|down\|status` ([PR-21 / #25](https://github.com/HyperdustLabs/OpenCOAT/pull/25)), `opencoat concern \| dcn \| inspect` ([PR-22 / #26](https://github.com/HyperdustLabs/OpenCOAT/pull/26)), `examples/06_long_running_daemon` ([PR-23 / #27](https://github.com/HyperdustLabs/OpenCOAT/pull/27)) |
| **M5** | OpenClaw host plugin | ✅ complete — event map ([#28](https://github.com/HyperdustLabs/OpenCOAT/pull/28)), injection + spans ([#29](https://github.com/HyperdustLabs/OpenCOAT/pull/29)), tool guard ([#30](https://github.com/HyperdustLabs/OpenCOAT/pull/30)), memory bridge + hooks ([#31](https://github.com/HyperdustLabs/OpenCOAT/pull/31)), `examples/04_openclaw_with_runtime` ([#32](https://github.com/HyperdustLabs/OpenCOAT/pull/32)) |
| M6 | Heartbeat + Meta governance workers | pending |
| M7 | Second host (langgraph/hermes) | pending |
| M8 | Postgres + Helm/K8s | pending |

The full per-PR M1 / M2 / M3 split lives in [`CONTRIBUTING.md`](CONTRIBUTING.md).

---

## Repository layout (monorepo)

```text
opencoat/
├── docs/                         # design docs, ADRs, concept guides, cookbooks
├── packages/
│   ├── opencoat-runtime-protocol/    # JSON schemas + pydantic envelopes (source of truth)
│   ├── opencoat-runtime-core/        # L2 pure logic: concern, joinpoint, pointcut, advice, weaving, copr, coordinator, resolver, dcn, meta, loops, ports
│   ├── opencoat-runtime-storage/     # ConcernStore / DCNStore backends (memory, sqlite, postgres, jsonl, vector)
│   ├── opencoat-runtime-llm/         # LLM / Embedder clients (openai, anthropic, azure, ollama, stub)
│   ├── opencoat-runtime-host-sdk/    # Host-side SDK (joinpoint emitter, injection consumer, transports)
│   ├── opencoat-runtime-daemon/      # Long-running runtime: scheduler, workers, IPC, HTTP/JSON-RPC API
│   ├── opencoat-runtime-cli/         # `opencoat` CLI: runtime up/down, concern list, replay, dcn visualize
│   └── opencoat-runtime-host-plugins/ # First-party host adapters (openclaw, hermes, langgraph, autogen, crewai, custom)
├── plugins/                      # out-of-tree plugin discovery (matchers, advisors, storage)
├── examples/                     # end-to-end usage examples
├── benchmarks/                   # extraction / matching / weaving benchmarks
├── tools/                        # codegen, schema check, perf dashboard
├── deploy/                       # docker-compose, kubernetes, helm, terraform
├── tests/                        # cross-package integration / e2e
└── scripts/                      # dev_up.sh, format.sh, release.sh
```

Detailed layout, module breakdown, schemas, protocol, and milestones are in
[`docs/design/v0.2-system-design.md`](docs/design/v0.2-system-design.md).

---

## Quick start

Requires Python 3.11+ and [`uv`](https://docs.astral.sh/uv/).

```bash
# Install workspace + every member package in editable mode (incl. dev extras)
uv sync --all-extras --dev

# Run all tests across the workspace (≈ 440 today, all green)
uv run pytest

# Validate JSON schemas + check generated pydantic models stay in sync
uv run python tools/schema_check.py
```

### Run the M1 demo

The smallest end-to-end agent is wired up in `examples/01_simple_chat_agent/`.
It uses in-memory stores and a deterministic stub LLM, so it runs hermetically
in ≈ 50 ms with no API key required:

```bash
uv run python -m examples.01_simple_chat_agent.main

# or with your own prompts:
uv run python -m examples.01_simple_chat_agent.main \
  "Who invented OpenCOAT?" "Tell me how concerns are matched."
```

Each turn shows the matched concerns, woven injection, and verifier verdicts —
read [`examples/01_simple_chat_agent/README.md`](examples/01_simple_chat_agent/README.md)
to see what each line of the host code exercises.

### Persist concerns + DCN (M3)

[`examples/03_persistent_agent_demo/`](examples/03_persistent_agent_demo/README.md)
uses `SqliteConcernStore` and `SqliteDCNStore` on one database file and
optionally writes `session.jsonl` for `opencoat replay`:

```bash
uv run python -m examples.03_persistent_agent_demo.main
```

### Plug in a real LLM (M2)

To swap the stub for a real provider, install the matching extra and pass an
`OpenAILLMClient` (or any other adapter from `opencoat_runtime_llm`) into the
runtime:

```bash
pip install "opencoat-runtime-llm[openai]"
export OPENAI_API_KEY=sk-...
```

```python
from opencoat_runtime_core import OpenCOATRuntime, RuntimeConfig
from opencoat_runtime_llm import OpenAILLMClient
from opencoat_runtime_storage.memory import MemoryConcernStore, MemoryDCNStore

runtime = OpenCOATRuntime(
    RuntimeConfig(),
    concern_store=MemoryConcernStore(),
    dcn_store=MemoryDCNStore(),
    llm=OpenAILLMClient(model="gpt-4o-mini"),
)
```

The same client works against any OpenAI-compatible gateway (Azure, vLLM,
OpenRouter, TogetherAI, …) by setting `base_url=`. See
[`packages/opencoat-runtime-llm/README.md`](packages/opencoat-runtime-llm/README.md)
for the full surface.

---

## Contributing

All changes land via pull request — branch protection on `main` requires CI
green and a linear history. The full workflow, branching model, PR sizing,
and local verification steps are in [`CONTRIBUTING.md`](CONTRIBUTING.md), which
also tracks the per-PR breakdown for each milestone.

```bash
git switch -c feat/m2-<scope>
# ... edit ...
./scripts/verify.sh        # local mirror of CI
git push -u origin HEAD     # then open a PR on GitHub
```

---

## Concept primer

- **Concern** — first-class runtime unit. Persistable, activatable, injectable, verifiable, evolvable, relatable. The runtime only distinguishes `kind: concern | meta_concern`; semantic types (`generated_type`) are produced by LLM, not enumerated by the runtime.
- **DCN (Deep Concern Network)** — long-term graph of concerns, relations, activation history.
- **Joinpoint** — observable point in the agent's thinking pipeline (8 levels: runtime / lifecycle / message / prompt-section / span / token / structure-field / thought-unit).
- **Pointcut** — activation rule (lifecycle / role / prompt-path / keyword / regex / semantic / structure / token / claim / confidence / risk / history).
- **Advice** — guidance/constraint produced when a concern activates (11 types).
- **Weaving** — projecting advice into the host's prompt / span / token / tool / memory / output / verification / reflection layer (11 operations).
- **COPR (Concern-Oriented Prompt Representation)** — structured prompt tree replacing flat strings, so pointcuts can match at sub-message granularity.
- **Concern Vector** — sparse activation snapshot for the current turn.
- **Concern Injection** — final, host-consumable advice payload, output of weaving.

See [`docs/design/v0.1-complete-design.md`](docs/design/v0.1-complete-design.md) for the conceptual definition,
and [`docs/design/v0.2-system-design.md`](docs/design/v0.2-system-design.md) for the engineering layout.

---

## License

Apache-2.0. See [LICENSE](LICENSE).
