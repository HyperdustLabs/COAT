# OpenCOAT ↔ OpenClaw bridge

TypeScript **OpenClaw gateway plugin** that forwards real agent hooks to the
OpenCOAT daemon (`joinpoint.submit` over HTTP JSON-RPC) and folds
`ConcernInjection` advice back into the prompt / tool path.

This closes the gap left by `opencoat plugin install openclaw` (Python scaffold
only): OpenClaw loads **npm/TS extensions** from `~/.openclaw/extensions/`, not
the generated `opencoat_plugin/` folder.

## Hook → joinpoint mapping

| OpenClaw hook | OpenCOAT joinpoint | Effect |
| --- | --- | --- |
| `message_received` | `on_user_input` | Submit + buffer injection |
| `before_prompt_build` | `before_response` | Submit + `prependSystemContext` |
| `before_tool_call` | `before_tool_call` | Submit + `{ block, blockReason }` when `tool_guard` |
| `session_start` | `runtime_start` | Submit (e.g. `demo-prompt-prefix`) |

## Prerequisites

1. Daemon running: `opencoat runtime up`
2. Concerns in the daemon store: `opencoat concern extract …` and/or `opencoat concern import --demo`
3. OpenClaw gateway **≥ 2026.3.24** with plugin prompt injection allowed

## Install (recommended)

From the COAT repo (builds TS, links into `~/.openclaw/extensions/`, merges config):

```bash
openclaw plugins install -l /path/to/COAT/integrations/openclaw-opencoat-bridge
openclaw gateway restart
```

OpenClaw requires scoped plugin ids in **`@scope/name`** form. The on-disk folder is
flat (no slash), e.g. `~/.openclaw/extensions/@hyperdust-opencoat-bridge`.

Verify:

```bash
openclaw plugins list   # @hyperdust/opencoat-bridge → loaded
grep opencoat-bridge ~/.openclaw/logs/gateway.log   # [opencoat-bridge] registered
```

Alternative helper (same symlink + `openclaw.json` merge):

```bash
./integrations/openclaw-opencoat-bridge/scripts/install-local.sh
openclaw plugins install -l /path/to/COAT/integrations/openclaw-opencoat-bridge
openclaw gateway restart
```

Manual `plugins.entries` key must be **`@hyperdust/opencoat-bridge`** (with slash),
not `@hyperdust-opencoat-bridge`. Set `daemonUrl` in plugin config (not `process.env`
in the plugin — OpenClaw blocks env+network patterns at install time).

## Verify

1. Chat in OpenClaw (Telegram / CLI) with text that matches your concern keywords, e.g. `Never run rm -rf in shell.`
2. Check DCN activations (should **not** be only `jp-manual-*`):

```bash
curl -sS http://127.0.0.1:7878/rpc -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","method":"dcn.activation_log","params":{"limit":10},"id":1}' \
  | python3 -m json.tool
```

3. Gateway logs should include `[opencoat-bridge] registered` and optional activation lines when `logActivations` is true.

## Configuration

| Field | Default | Description |
| --- | --- | --- |
| `daemonUrl` | `http://127.0.0.1:7878/rpc` | JSON-RPC endpoint (set in `plugins.entries` config) |
| `enabled` | `true` | Set `false` to no-op (hooks still register) |
| `logActivations` | `false` | Log matched concern ids per joinpoint |

## Limitations (v0.1 bridge)

- Prompt folding uses `prependSystemContext` only (not full dotted-path injector parity with Python `OpenClawInjector`).
- `before_memory_write` / memory bridge not wired yet.
- Double joinpoint fire (`on_user_input` + `before_response`) is intentional when concerns list both.

See also: [`examples/04_openclaw_with_runtime/README.md`](../../examples/04_openclaw_with_runtime/README.md) (toy bus) and [`docs/design/v0.2-system-design.md`](../../docs/design/v0.2-system-design.md) §4.7.1.
