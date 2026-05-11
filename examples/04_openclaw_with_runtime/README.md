# 04 — OpenClaw + COAT Runtime

End-to-end demo: a toy **OpenClaw-shaped** event bus drives
`COATRuntime` through `COAT_runtime_host_openclaw` — the same surface
M5 ships in PRs [#28](https://github.com/HyperdustLabs/COAT/pull/28)–[#31](https://github.com/HyperdustLabs/COAT/pull/31) (`OpenClawAdapter`,
`OpenClawInjector`, `OpenClawToolGuard`, `install_hooks`, `OpenClawMemoryBridge`).

There is **no** upstream OpenClaw SDK in this repo. The example uses a
~30-line in-memory `subscribe` / `fire` host so CI stays hermetic while
still exercising the real hook wiring.

## What it does

1. Builds an in-process `COATRuntime` (memory stores + stub LLM).
2. Seeds two demo concerns (`examples/04_openclaw_with_runtime/concerns.py`)
   into both the concern store **and** the DCN graph (required for
   `MemoryDCNStore.log_activation`).
3. Calls `install_hooks(...)` with a narrow `event_names=` tuple:
   `agent.started`, `agent.user_message`, `agent.memory_write`.
4. Replays a canned lifecycle on the toy bus, then `uninstall()`s so
   no callbacks leak.
5. Prints the last `ConcernInjection` and a short DCN activation summary.

## Run

```bash
uv run python -m examples.04_openclaw_with_runtime.main
```

Quiet mode (structured smoke — no stdout):

```bash
uv run python -m examples.04_openclaw_with_runtime.main --quiet
```

## Programmatic API

`run_demo()` returns an `OpenClawDemoReport` dataclass (turn-loop
injection snapshot, DCN activation counts, uninstall hygiene). The
integration test in `tests/integration/test_example_openclaw_with_runtime.py`
imports the example via `importlib` because the folder name starts with
a digit.
