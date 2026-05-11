# COAT-runtime-cli

`COATr` — command-line interface for the COAT Runtime. Talks to a local
daemon over stdlib HTTP JSON-RPC (M4 PR-19), or replays a recorded
session locally without a daemon.

```bash
COATr runtime up --config /etc/coat/daemon.yaml --pid-file /run/coat.pid
COATr runtime status --pid-file /run/coat.pid
COATr runtime down --pid-file /run/coat.pid
COATr replay session.jsonl
```

## `COATr runtime` (M4 PR-21)

`up | down | status | reload` manage the long-running daemon over its
HTTP JSON-RPC listener:

| Action | Behaviour |
| --- | --- |
| `up`    | Loads the daemon config to discover `ipc.http`, then double-forks `python -m COAT_runtime_daemon` so the new process is owned by `init`. Polls `health.ping` until the listener answers or `--wait-seconds` expires. |
| `down`  | Reads the daemon PID from `--pid-file` and sends `SIGTERM` (`--force` upgrades to `SIGKILL`). Polls until the process is gone. |
| `status`| POSTs `health.ping`. Exits `0` when the daemon answers, `3` when it is stopped (connection refused), `4` when degraded. Reports any `--pid-file` it can read. |
| `reload`| Deferred — wiring `Daemon.reload()` over RPC lands in a later PR. Returns a clean error today. |

Endpoint resolution: `--host` / `--port` / `--path` always win; failing
those the CLI reads `ipc.http` from `--config` (default daemon
configuration when omitted). The same flags work across all three
actions so the same shell snippet covers the full lifecycle.

```bash
COATr runtime up    --config daemon.yaml --pid-file /tmp/coat.pid
COATr runtime status --pid-file /tmp/coat.pid    # → endpoint + pid state
COATr runtime down  --pid-file /tmp/coat.pid     # → SIGTERM, polls
```

The underlying HTTP JSON-RPC client lives in
`COAT_runtime_cli.transport.HttpRpcClient`; it is stdlib-only
(`http.client` + `json`) and raises typed `HttpRpcConnectionError` /
`HttpRpcProtocolError` / `HttpRpcCallError` so callers can branch on
*daemon stopped* vs *daemon answered with an error*.

## Other subcommands

`COATr replay session.jsonl` replays a JSONL session recorded via
`COAT_runtime_storage.jsonl.SessionJsonlRecorder` (M3).
`COATr concern`, `COATr dcn`, `COATr inspect`, and `COATr plugin` remain
stubs until later M4 PRs (PR-22 wires `concern` + `dcn` + `inspect`).
