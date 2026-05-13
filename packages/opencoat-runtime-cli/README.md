# opencoat-runtime-cli

`opencoat` — command-line interface for the OpenCOAT Runtime. Talks to a local
daemon over stdlib HTTP JSON-RPC (M4 PR-19), or replays a recorded
session locally without a daemon.

```bash
opencoat runtime up --config /etc/opencoat/daemon.yaml --pid-file /run/opencoat.pid
opencoat runtime status --pid-file /run/opencoat.pid
opencoat runtime down --pid-file /run/opencoat.pid
opencoat replay session.jsonl
```

## `opencoat runtime` (M4 PR-21)

`up | down | status | reload` manage the long-running daemon over its
HTTP JSON-RPC listener:

| Action | Behaviour |
| --- | --- |
| `up`    | Loads the daemon config to discover `ipc.http`, then double-forks `python -m opencoat_runtime_daemon` so the new process is owned by `init`. Polls `health.ping` until the listener answers or `--wait-seconds` expires. |
| `down`  | Reads the daemon PID from `--pid-file` and sends `SIGTERM` (`--force` upgrades to `SIGKILL`). Polls until the process is gone. |
| `status`| POSTs `health.ping`. Exits `0` when the daemon answers, `3` when it is stopped (connection refused), `4` when degraded. Reports any `--pid-file` it can read. |
| `reload`| Deferred — wiring `Daemon.reload()` over RPC lands in a later PR. Returns a clean error today. |

Endpoint resolution: `--host` / `--port` / `--path` always win; failing
those the CLI reads `ipc.http` from `--config` (default daemon
configuration when omitted). The same flags work across all three
actions so the same shell snippet covers the full lifecycle.

```bash
opencoat runtime up    --config daemon.yaml --pid-file /tmp/opencoat.pid
opencoat runtime status --pid-file /tmp/opencoat.pid    # → endpoint + pid state
opencoat runtime down  --pid-file /tmp/opencoat.pid     # → SIGTERM, polls
```

The underlying HTTP JSON-RPC client lives in
`opencoat_runtime_cli.transport.HttpRpcClient`; it is stdlib-only
(`http.client` + `json`) and raises typed `HttpRpcConnectionError` /
`HttpRpcProtocolError` / `HttpRpcCallError` so callers can branch on
*daemon stopped* vs *daemon answered with an error*.

## `opencoat concern` (M4 PR-22)

`opencoat concern` talks to the daemon over HTTP JSON-RPC:

| Action | Wire | Notes |
| --- | --- | --- |
| `list`   | `concern.list`   | Default output is `<id>  <state>  <name>` columns. `--kind` / `--tag` / `--lifecycle-state` / `--limit` filter rows; `--json` emits a JSON array. |
| `show ID`| `concern.get`    | Pretty-prints the concern JSON. Exit `1` if the id is unknown. |
| `import PATH` | `concern.upsert` | Accepts JSON or YAML, either a single mapping or a list of mappings. |
| `export [ID] [-o PATH]` | `concern.list` / `concern.get` | Without `ID` exports every concern; otherwise exports one as a singleton array. |
| `diff A B` | `concern.get` × 2 | Unified diff over canonical JSON. |

```bash
opencoat concern list --lifecycle-state active
opencoat concern export -o /tmp/concerns.json
opencoat concern import /tmp/concerns.json
opencoat concern diff c-1 c-2
```

## `opencoat dcn` (M4 PR-22)

A clean *full* DCN export will arrive when the `DCNStore` port exposes
enumeration over RPC. Today the CLI ships the *shallow* snapshot the
existing RPC surface can deliver — the concern list plus the
activation history — which is enough to drive visualisation:

| Action | Wire | Notes |
| --- | --- | --- |
| `activation-log` | `dcn.activation_log` | `--concern-id`, `--limit`, `--json`. |
| `export --format json` | `concern.list` + `dcn.activation_log` | Combined JSON snapshot. |
| `export --format dot` (or `visualize`) | same, then `dcn_to_dot()` | Joinpoints render as ovals, concerns as boxes, edges = activations. |
| `import` | — | Reserved for a future PR; needs write API on `DCNStore`. |

```bash
opencoat dcn activation-log --limit 50
opencoat dcn export --format dot -o dcn.dot && dot -Tsvg dcn.dot -o dcn.svg
```

## `opencoat inspect` (M4 PR-22)

`inspect` reads the catalogs baked into `opencoat_runtime_core`, so it
works without a running daemon:

| Target | Source |
| --- | --- |
| `joinpoints` | `opencoat_runtime_core.joinpoint.JOINPOINT_CATALOG` (v0.1 §12.3–§12.6). |
| `pointcuts`  | The 12 strategies under `opencoat_runtime_core.pointcut.strategies` (v0.1 §13.2). |

```bash
opencoat inspect joinpoints
opencoat inspect pointcuts
```

## Other subcommands

`opencoat replay session.jsonl` replays a JSONL session recorded via
`opencoat_runtime_storage.jsonl.SessionJsonlRecorder` (M3).
`opencoat plugin` remains a stub until M5.
