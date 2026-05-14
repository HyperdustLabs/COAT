# OpenCOAT — read-only inspection commands

Everything in this file is **safe to run against a live daemon**: no
command in the `concern` / `dcn` / `inspect` / `replay` groups mutates
state when used as documented below.

The wire path is HTTP JSON-RPC on `127.0.0.1:7878/rpc` by default; pass
`--host` / `--port` / `--path` (or `--config`) to override.

## `opencoat concern` — concern table

| command | wire | what it returns |
| --- | --- | --- |
| `opencoat concern list` | `concern.list` | one row per concern: `<id>  <state>  <name>` |
| `opencoat concern list --lifecycle-state active` | `concern.list` | filter to active rows only |
| `opencoat concern list --kind concern` | `concern.list` | filter by kind (`concern` or `meta_concern`) |
| `opencoat concern list --tag demo` | `concern.list` | filter by `tags[]` membership |
| `opencoat concern list --json` | `concern.list` | machine-readable JSON array |
| `opencoat concern show <id>` | `concern.get` | pretty-prints the full Concern as JSON |
| `opencoat concern export -o concerns.json` | `concern.list` + `concern.get` | dumps every concern to disk as JSON |
| `opencoat concern export <id> -o one.json` | `concern.get` | dumps one concern as a singleton array |
| `opencoat concern diff <a> <b>` | `concern.get` × 2 | unified diff over canonical JSON |

A small recipe — "what's currently changing the prompt?":

```bash
opencoat concern list --lifecycle-state active --json \
  | jq '.[] | select(.advice.type == "PROMPT_PREFIX" or .advice.type == "RESPONSE_REQUIREMENT") | {id, name, advice: .advice.type}'
```

## `opencoat dcn` — Deep Concern Network

The DCN is the long-lived graph of concerns + activation history. The
write surface is intentionally not exposed in M5; today's snapshot is
shallow but enough to drive visualisation and convergence sanity checks.

| command | wire | notes |
| --- | --- | --- |
| `opencoat dcn activation-log --limit 50` | `dcn.activation_log` | most recent activations, newest first |
| `opencoat dcn activation-log --concern-id <id>` | `dcn.activation_log` | filter to one concern |
| `opencoat dcn export --format json -o dcn.json` | `concern.list` + `dcn.activation_log` | combined snapshot |
| `opencoat dcn export --format dot -o dcn.dot` | same, then `dcn_to_dot()` | Graphviz DOT |
| `opencoat dcn visualize -o dcn.dot` | alias of `export --format dot` | shorter form |

Render the DOT:

```bash
opencoat dcn export --format dot -o dcn.dot
dot -Tsvg dcn.dot -o dcn.svg
```

Joinpoints render as ovals, concerns as boxes, edges as activations.
Edge thickness scales with the activation count in the current window.

## `opencoat inspect` — runtime catalogs (no daemon needed)

`inspect` reads the catalogs baked into `opencoat_runtime_core`, so it
works offline:

| command | source |
| --- | --- |
| `opencoat inspect joinpoints` | `opencoat_runtime_core.joinpoint.JOINPOINT_CATALOG` |
| `opencoat inspect pointcuts` | the 12 strategies under `opencoat_runtime_core.pointcut.strategies` |

Use these to confirm a pointcut you're authoring will actually compile,
or to discover the canonical joinpoint id for a host event you're
trying to subscribe to.

## `opencoat replay` — JSONL session replay

If the daemon was started with the JSONL recorder enabled, every
joinpoint and injection is appended to a session file. `replay` re-feeds
those joinpoints into a fresh runtime and shows the diff between the
recorded injections and what a clean re-run would produce.

```bash
opencoat replay session.jsonl
opencoat replay session.jsonl --strict          # exit 1 on any divergence
opencoat replay session.jsonl --concern <id>    # replay only one concern's path
```

Replay always uses `MemoryConcernStore` + `MemoryDCNStore` + the
deterministic `StubLLMClient`, so it never touches the live daemon's
state — safe to run while the daemon is up.

## LLM credentials (no keys in chat)

Coding agents must **not** ask users to paste `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`
/ Azure secrets into an agent chat. Use a **local terminal** and on-disk files
instead.

**Probe** (daemon HTTP JSON-RPC must be up — default `http://127.0.0.1:7878/rpc`):

```bash
curl -sS -X POST http://127.0.0.1:7878/rpc \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"runtime.llm_info","params":{}}'
```

If `"real": false` and `"label"` mentions `stub`, configure credentials **outside chat**:

```bash
opencoat configure llm          # wizard: ~/.opencoat/opencoat.env or inline YAML
opencoat service restart        # or: runtime down && runtime up
```

The daemon entrypoint merges **allow-listed** LLM variables from
`~/.opencoat/opencoat.env` into its process environment on startup (before
YAML), so `runtime up` / `opencoat service` pick up wizard env-file keys
without a manual `source`. Optional: `source` the file in your shell if you
want the same exports for other local tools.

**Non-interactive** (human runs in a shell that **already** exports the key — the
agent never pastes the secret):

```bash
opencoat configure llm --non-interactive --provider openai --openai-api-key "$OPENAI_API_KEY"
```

**`opencoat service install` + env-file mode:** the LaunchAgent / systemd unit
runs `python -m opencoat_runtime_daemon`, which performs the same env-file
merge as `runtime up`. You only need extra `EnvironmentFile=` lines if you
keep secrets **outside** `~/.opencoat/opencoat.env` or use non-allow-listed
variable names (then export them in the service environment yourself).
See `opencoat configure llm` footer text after it runs.

## Daemon health

Independent of the data plane:

```bash
opencoat runtime status --pid-file .opencoat/opencoat.pid
# exit 0 = healthy, 3 = stopped, 4 = degraded
```

`status` is also the safest probe for "is the JSON-RPC listener up?" —
it issues a `health.ping` and reports the endpoint it answered on.
