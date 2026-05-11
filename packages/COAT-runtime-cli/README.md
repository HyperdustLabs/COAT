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

## `COATr concern` (M4 PR-22)

`COATr concern` talks to the daemon over HTTP JSON-RPC:

| Action | Wire | Notes |
| --- | --- | --- |
| `list`   | `concern.list`   | Default output is `<id>  <state>  <name>` columns. `--kind` / `--tag` / `--lifecycle-state` / `--limit` filter rows; `--json` emits a JSON array. |
| `show ID`| `concern.get`    | Pretty-prints the concern JSON. Exit `1` if the id is unknown. |
| `import PATH` | `concern.upsert` | Accepts JSON or YAML, either a single mapping or a list of mappings. |
| `export [ID] [-o PATH]` | `concern.list` / `concern.get` | Without `ID` exports every concern; otherwise exports one as a singleton array. |
| `diff A B` | `concern.get` × 2 | Unified diff over canonical JSON. |

```bash
COATr concern list --lifecycle-state active
COATr concern export -o /tmp/concerns.json
COATr concern import /tmp/concerns.json
COATr concern diff c-1 c-2
```

## `COATr dcn` (M4 PR-22)

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
COATr dcn activation-log --limit 50
COATr dcn export --format dot -o dcn.dot && dot -Tsvg dcn.dot -o dcn.svg
```

## `COATr inspect` (M4 PR-22)

`inspect` reads the catalogs baked into `COAT_runtime_core`, so it
works without a running daemon:

| Target | Source |
| --- | --- |
| `joinpoints` | `COAT_runtime_core.joinpoint.JOINPOINT_CATALOG` (v0.1 §12.3–§12.6). |
| `pointcuts`  | The 12 strategies under `COAT_runtime_core.pointcut.strategies` (v0.1 §13.2). |

```bash
COATr inspect joinpoints
COATr inspect pointcuts
```

## Other subcommands

`COATr replay session.jsonl` replays a JSONL session recorded via
`COAT_runtime_storage.jsonl.SessionJsonlRecorder` (M3).
`COATr plugin` remains a stub until M5.
