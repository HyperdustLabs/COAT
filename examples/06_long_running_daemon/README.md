# 06 — Long-running daemon (M4 PR-23)

End-to-end demo of the M4 stack: a real
[`opencoat_runtime_daemon.Daemon`](../../packages/opencoat-runtime-daemon/opencoat_runtime_daemon/daemon.py)
serving JSON-RPC over HTTP, driven from the same
[`HttpRpcClient`](../../packages/opencoat-runtime-cli/opencoat_runtime_cli/transport.py)
that backs `opencoat concern` / `opencoat dcn` / `opencoat runtime status`. If
this example runs green, PR-17 through PR-22 compose correctly.

## Layout

```text
examples/06_long_running_daemon/
├── README.md       ← you are here
├── __init__.py
├── concerns.py     # same three rules as example 03 (Be concise / Cite / No-PII)
└── main.py         # programmatic Daemon ↔ HttpRpcClient tour
```

## What the tour does

1. Picks a free loopback port (sidesteps `Daemon._maybe_start_http`'s
   `port or 7878` fallback, which would clobber `port=0`).
2. Composes a `DaemonConfig` overlaying `ipc.http.enabled=true` on top
   of the bundled `default.yaml`, plus sqlite storage at
   `./.opencoat-daemon-demo/state.db` (or `--in-memory`).
3. `Daemon.start()` builds the runtime, mounts the HTTP server in a
   background thread, and writes a PID file.
4. From the main thread, an `HttpRpcClient` runs:
   * `health.ping`
   * `concern.list` (initial — empty on first run)
   * `concern.upsert × N` — idempotent seed, only writes missing rows
   * `joinpoint.submit × 3` — three demo events that exercise different
     pointcut keywords (`?`, `tell`, `email`)
   * `concern.list` again — to show activation counters moved
   * `dcn.activation_log` — to show the history rows
   * `runtime.snapshot` — the same shape `opencoat runtime status`
     surfaces under the hood
5. Optionally renders the activation snapshot via
   [`dcn_to_dot`](../../packages/opencoat-runtime-cli/opencoat_runtime_cli/visualize/dcn_dot.py)
   to a `.dot` file (`--dot-out`).
6. `Daemon.stop()` drains HTTP, closes sqlite, and releases the PID
   file.

## Run it

```bash
uv run python -m examples.06_long_running_daemon.main
```

Useful flags:

```bash
# Use a fixed port (handy when you want to point opencoat at it):
uv run python -m examples.06_long_running_daemon.main --port 17890

# Explicitly ask for an OS-assigned free port (same as omitting --port).
uv run python -m examples.06_long_running_daemon.main --port 0

# Don't touch sqlite — pure memory backends.
uv run python -m examples.06_long_running_daemon.main --in-memory

# Render a DOT file via dcn_to_dot:
uv run python -m examples.06_long_running_daemon.main --dot-out /tmp/dcn.dot
dot -Tsvg /tmp/dcn.dot -o /tmp/dcn.svg

# Keep the daemon up so you can drive it from `opencoat` in another shell:
uv run python -m examples.06_long_running_daemon.main --keep-running --port 17890
```

## Drive it from `opencoat` (PR-21 / PR-22)

With `--keep-running --port 17890`:

```bash
opencoat runtime status --port 17890 --pid-file ./.opencoat-daemon-demo/opencoat.pid
opencoat concern list   --port 17890
opencoat concern show   c-cite --port 17890
opencoat dcn activation-log --port 17890
opencoat dcn export   --format dot --port 17890 -o /tmp/dcn.dot
```

## Why is this in `examples/` and not `tests/`?

It is *both*. `tests/integration/test_example_long_running_daemon.py`
imports the module via `importlib` (the folder starts with a digit, so
no implicit package import) and runs the tour against an in-memory
daemon as part of the regular pytest suite. The same module also
ships under `examples/` because the M4 ergonomics story — *one
process, one CLI, one RPC* — is easier to internalise from running
code than from any amount of prose.

## Related code

| Piece | Location |
| --- | --- |
| `Daemon` lifecycle | `opencoat_runtime_daemon.daemon` ([PR-20 / #24](https://github.com/HyperdustLabs/COAT/pull/24)) |
| HTTP server | `opencoat_runtime_daemon.ipc.http_server` ([PR-19 / #23](https://github.com/HyperdustLabs/COAT/pull/23)) |
| JSON-RPC dispatcher | `opencoat_runtime_daemon.ipc.jsonrpc_dispatch` ([PR-18 / #22](https://github.com/HyperdustLabs/COAT/pull/22)) |
| `build_runtime` | `opencoat_runtime_daemon.runtime_builder` ([PR-17 / #21](https://github.com/HyperdustLabs/COAT/pull/21)) |
| HTTP client + `opencoat runtime` | `opencoat_runtime_cli.transport`, `commands/runtime_cmd.py` ([PR-21 / #25](https://github.com/HyperdustLabs/COAT/pull/25)) |
| `opencoat concern / dcn / inspect` | `opencoat_runtime_cli.commands.{concern,dcn,inspect}_cmd` ([PR-22 / #26](https://github.com/HyperdustLabs/COAT/pull/26)) |
