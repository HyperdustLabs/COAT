---
name: opencoat
description: >-
  Hosts send one line: Read https://www.opencoat.ai/SKILL.md to install and use OpenCOAT.
  The skill defines the full agent contract (run Quick start on the user's machine,
  daemon + autostart, LLM checks without keys in chat, demo). Also: concern-driven
  joinpoints / pointcuts / advice / weaving on Cursor, Claude Code, OpenClaw, LangGraph, custom.
---

## Canonical host prompt (copy verbatim)

The human may send **only** this line to their host agent — no other
instructions are required; everything else is in this document and linked
files:

```text
Read https://www.opencoat.ai/SKILL.md to install and use OpenCOAT.
```

### Agent contract

If that sentence is your **sole** instruction, **fetch** this URL (and pull
companion files when this SKILL tells you to), then **run** OpenCOAT on the
user's machine per **Quick start** until the daemon is healthy and the demo
path succeeds — not a passive read-through. Security and LLM rules (including
**never asking for API keys in chat**) live here and in [rules.md](rules.md);
the human does not need to paste them again.

# OpenCOAT — Concern-Oriented Agent Thinking Runtime

OpenCOAT runs alongside any host agent and rewrites its joinpoints
(`runtime_start`, `before_tool_call`, `before_memory_write`, …) using
**Concerns** — first-class units that carry a pointcut, an advice, and a
weaving policy. The result is a small, observable, replayable layer that
sits between the host's prompt/tool loop and the model.

This skill is the "5-minute install" that makes the runtime visible:

1. install the CLI + host SDK,
2. start a local daemon (zero-config HTTP on `127.0.0.1:7878/rpc`) **and** register OS autostart (`opencoat service install` on macOS / Linux),
3. import the 3 dramatic demo concerns,
4. emit a few joinpoints and watch them light up activations,
5. inspect the Deep Concern Network (DCN),
6. leave the daemon running (it's long-lived by design — tear down only if you really want to).

> Source repo: <https://github.com/HyperdustLabs/OpenCOAT>  
> Skill repo:  <https://github.com/HyperdustLabs/opencoat-skill>  
> Skill served at: <https://www.opencoat.ai/SKILL.md>

---

## Self-install (for AI agents)

Drop the six skill files into whatever your host calls its skills directory
(Cursor: `~/.cursor/skills/opencoat/`, Claude Code: `~/.claude/skills/opencoat/`,
etc.) and reload:

```bash
DEST="${SKILLS_DIR:-$HOME/.cursor/skills}/opencoat"
mkdir -p "$DEST"
for f in SKILL.md concerns.md inspection.md rules.md skill.json bootstrap_daemon.sh; do
  curl -fsSL "https://www.opencoat.ai/$f" -o "$DEST/$f"
done
chmod +x "$DEST/bootstrap_daemon.sh" 2>/dev/null || true
echo "installed opencoat skill → $DEST"
```

Each URL is a thin proxy onto this repo's `main` branch — see
[`DEPLOY.md`](https://github.com/HyperdustLabs/opencoat-skill/blob/main/DEPLOY.md) for the worker + CDN setup. `curl -I` any
URL to see the `X-Skill-Source: github:HyperdustLabs/opencoat-skill@main/<file>`
header that records exactly what you fetched.

After the skill files are on disk, execute **Quick start** below on the
user's machine — the canonical one-line prompt above does not change that
obligation.

---

## Quick start (≤5 min)

Copy this checklist and walk through it top-to-bottom:

```text
- [ ] Step 1: install the CLI + host SDK
- [ ] Step 2: start the daemon + OS autostart (LaunchAgent / systemd user)
- [ ] Step 2b: verify LLM wiring (see **LLM credentials check** — no API keys in chat)
- [ ] Step 3: import the 3 demo concerns
- [ ] Step 4a: `opencoat demo` — see concerns change host behavior
- [ ] Step 4b (optional): wire an OpenClaw host plugin
- [ ] Step 5: inspect the DCN
- [ ] Step 6: leave the daemon running (optional teardown)
```

### Step 1 — install

OpenCOAT ships as three packages out of the monorepo at
<https://github.com/HyperdustLabs/OpenCOAT>:

| package | what it is |
| --- | --- |
| `opencoat-runtime-protocol` | wire envelopes + JSON Schemas (pulled in transitively) |
| `opencoat-runtime` | runtime core + daemon + `opencoat` CLI |
| `opencoat-runtime-host` | host SDK (`Client`, `JoinpointEmitter`) + OpenClaw adapter |

Both packages are on PyPI. The recommended path is `pipx` — it puts
the `opencoat` CLI on `PATH` without polluting the host agent's
Python, and `pipx inject` adds the host SDK to the same isolated env
so `opencoat demo`'s lazy imports succeed:

```bash
pipx install opencoat-runtime
pipx inject  opencoat-runtime opencoat-runtime-host

opencoat --version    # → 0.1.x
```

`opencoat-runtime-protocol` comes along transitively — you don't need
to name it. `pipx inject` is what wires `opencoat-runtime-host` into
the CLI's env; if you skip it, `opencoat demo` will refuse to start
with a `ModuleNotFoundError: opencoat_runtime_host_sdk`.

### Step 1b (alternative) — install into a regular venv

If your host agent is itself a Python project that wants to `import
opencoat_runtime_host_sdk` from its own code (writing a custom host,
embedding the runtime in-process, etc.), drop the pipx layer and use
a plain venv:

```bash
python3 -m venv .opencoat/venv
source .opencoat/venv/bin/activate
pip install opencoat-runtime opencoat-runtime-host

opencoat --version    # → 0.1.x
```

The CLI works identically; the difference is just *where* the SDK
ends up on `sys.path`.

### Step 2 — start the daemon + OS autostart (long-running, persistent)

The bundled daemon defaults (current `opencoat-runtime`) enable HTTP JSON-RPC
on `127.0.0.1:7878/rpc` and **sqlite** persistence under `~/.opencoat/`. After
Step 1, bring the daemon up and register a user-level autostart unit so it
survives terminal closes **and** host-agent (Cursor / OpenClaw / …) restarts.

**Recommended one-shot (copy-paste):**

```bash
mkdir -p ~/.opencoat
opencoat runtime up
opencoat runtime status
opencoat service install    # macOS LaunchAgent · Linux systemd --user
opencoat service status
```

Or run the bundled helper from an OpenCOAT git checkout:
`bash integrations/opencoat-skill/bootstrap_daemon.sh` (same commands inside).

Default PID file is `~/.opencoat/opencoat.pid` — you only need `--pid-file` if
you override it. `runtime up` double-forks so the process is not tied to this
shell.

**PyPI / CLI drift:** `opencoat service …` (LaunchAgent / systemd autostart)
ships in **`opencoat-runtime` 0.1.2+**. If `opencoat service` is missing
(unknown subcommand / parser error), upgrade the CLI env:

```bash
pip install -U 'opencoat-runtime>=0.1.2' 'opencoat-runtime-host>=0.1.2'
# pipx:
pipx upgrade opencoat-runtime && pipx inject opencoat-runtime opencoat-runtime-host
```

Until then, keep using `opencoat runtime up` + `opencoat runtime status` and
start the daemon manually after reboot (no OS-level autostart).

**Custom sqlite paths or HTTP bind:** run `opencoat configure daemon` (and
optionally `opencoat configure llm`), then:

```bash
opencoat runtime up --config ~/.opencoat/daemon.yaml
opencoat service install --config ~/.opencoat/daemon.yaml
```

Pass `--port` / `--host` to `runtime up` / `status` if 7878 is busy.

**Hermetic CI / pytest / no autostart:** do **not** run `opencoat service
install` inside automated tests. For in-process tests that call
`load_config()`, set `OPENCOAT_TEST_MEMORY_STORES=1` so stores stay in RAM and
never touch `~/.opencoat/*.sqlite`. For a disposable daemon without OS
service registration:

```bash
mkdir -p ~/.opencoat
opencoat runtime up
opencoat runtime status
```

### LLM credentials check (**agents: never ask for keys in chat**)

After Step 2, confirm the daemon is not stuck on a **stub** LLM (no real
provider credentials). **Do not** ask the user to paste API keys into this
chat — use a local terminal and `opencoat configure llm` instead.

**Quick probe** (default JSON-RPC URL):

```bash
curl -sS -X POST http://127.0.0.1:7878/rpc \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"runtime.llm_info","params":{}}'
```

If `"real": false`, walk the human through the recipes in
[inspection.md — LLM credentials](inspection.md#llm-credentials-no-keys-in-chat)
(wizard, non-interactive shell-only path, and `opencoat service install` caveats).

### Step 3 — import the 3 demo concerns

```bash
opencoat concern import --demo
opencoat concern list
```

You should see exactly three rows:

```text
demo-prompt-prefix   active   Demo — runtime banner in system prompt
demo-tool-block      active   Demo — block destructive shell commands
demo-memory-tag      active   Demo — annotate every memory write
```

What each one does, and where it fires, is documented in
[concerns.md](concerns.md).

### Step 4a — see concerns change host behavior (one line)

```bash
opencoat demo
```

That's the whole step. The CLI subscribes a tiny in-script `FakeHost`
to the daemon via `install_hooks`, fires three events, and uses the
pickup API (`apply_to` / `guard_tool_call`) to fold the returned
advice back into the host's mutable state. Three scenes print
**BEFORE / AFTER** so concerns visibly change the host context:

```text
== OpenCOAT demo — daemon @ http://127.0.0.1:7878/rpc ==

[1/3] PROMPT FOLDING — concern: demo-prompt-prefix
  fire event : agent.started
  prompt slot: runtime_prompt.active_concerns
  BEFORE     : ""
  AFTER      : Begin every response with `[OpenCOAT demo active]`.
  → apply_to() folded demo-prompt-prefix into the prompt slot.

[2/3] TOOL GUARD — concern: demo-tool-block
  fire event : agent.before_tool (payload includes 'rm -rf')
  tool call  : shell.exec rm -rf /tmp/scratch
  outcome    : BLOCKED
  reason     : Refusing destructive shell command — `rm -rf` is blocked by demo-tool-block.
  → guard_tool_call() returned blocked=True. Host should refuse.

[3/3] MEMORY NOTE — concern: demo-memory-tag
  fire event : agent.memory_write
  memory slot: memory_write.policy_note
  BEFORE     : ""
  AFTER      : memory.policy=demo-memory-tag: write annotated by demo concern.
  → apply_to() annotated memory_write.policy_note.

✓ All three scenes produced visible host-context changes.
```

If the daemon isn't running yet (or you don't want to bother seeding
it), `opencoat demo --in-proc` builds an in-process runtime and
seeds the three demo concerns automatically — same three scenes, no
`opencoat runtime up` / `concern import` required.

Want to learn the underlying pattern? `opencoat demo --script-out
demo_host.py` writes the equivalent ~40-line Python file (the same
`install_hooks` → `apply_to` / `guard_tool_call` shape your own
host will use) to disk without running anything. That's the seed
for adapting the demo to a real host agent.

The two pickup points to remember:

- `installed.apply_to(context)` — fold every buffered advice row
  into a mutable host context (prompt slots, memory slots, …).
- `installed.guard_tool_call(call)` — decode `TOOL_GUARD` advice
  into a structured outcome you can branch on (`outcome.blocked` →
  refuse; `outcome.arguments` → dispatch with rewrites;
  `outcome.notes` → audit-only annotations).

### Step 4b — OpenClaw host plugin (optional)

If you're integrating OpenCOAT into a real OpenClaw-shaped host agent
(anything that exposes `subscribe(event_name, callback) -> unsubscribe`),
scaffold a plugin:

```bash
opencoat plugin install openclaw --out ./opencoat_plugin
```

Generates four lint-clean files in `./opencoat_plugin/`:

| file | role |
| --- | --- |
| `__init__.py` | makes the directory a package |
| `bootstrap_opencoat.py` | call once at host startup to register concerns + adapter |
| `host_adapter.py` | maps host events → OpenCOAT joinpoints (you only edit this) |
| `concerns.py` | three starter concerns (edit freely) |

Then, from your host's startup code:

```python
from opencoat_plugin.bootstrap_opencoat import install

installed = install(your_openclaw_host)   # default: daemon at $OPENCOAT_DAEMON_URL
try:
    while turn := your_openclaw_host.next_turn():
        # 1. events flow into the daemon automatically through the
        #    install_hooks subscriptions; concerns activate inside it.
        turn.run_until_prompt()

        # 2. fold every active advice row into the prompt context
        #    BEFORE calling the LLM. Empty buffer → identity.
        turn.prompt_ctx = installed.apply_to(turn.prompt_ctx)

        # 3. before dispatching each pending tool call, ask OpenCOAT
        #    whether any TOOL_GUARD advice applies. None → default-allow.
        for call in turn.pending_tool_calls():
            outcome = installed.guard_tool_call(call)
            if outcome is not None and outcome.blocked:
                turn.refuse(call, reason=outcome.block_reason)
            elif outcome is not None:
                turn.dispatch(call["name"], outcome.arguments, notes=outcome.notes)
            else:
                turn.dispatch(call["name"], call["arguments"])
finally:
    installed.uninstall()
```

`install()` connects to the running daemon over HTTP (the same daemon
you started in Step 2), so concerns + DCN state are shared with
`opencoat concern …` / `opencoat dcn …`. The two pickup points
(`apply_to` / `guard_tool_call`) are where OpenCOAT's advice materialises
back into your host — without them you'll see activations in the DCN
log but no visible change to the agent's prompt or tool dispatch.

For a one-process unit test where you don't want a daemon, swap
`install()` for `install_in_process()` — same signature + pickup API,
plus a bundled `OpenCOATRuntime` is returned.

For a non-OpenClaw host, swap `openclaw` for `custom` — the same four
files, with the adapter and joinpoint mapping stubbed for you to fill
in, plus a `daemon_client()` helper that returns a ready-to-use
`Client`.

### Step 5 — inspect

See [inspection.md](inspection.md) for the full surface. The two most
useful commands while activations are flowing:

```bash
opencoat concern list --lifecycle-state active
opencoat dcn activation-log --limit 20
```

Sample activation log after `demo_host.py`:

```text
2026-05-13T08:39:35  demo-memory-tag   62515cdf-…  score=0.675
2026-05-13T08:39:35  demo-prompt-prefix 7a221311-…  score=0.500
```

For a graph view:

```bash
opencoat dcn export --format dot -o dcn.dot
dot -Tsvg dcn.dot -o dcn.svg && open dcn.svg
```

### Step 6 — keep it running (or tear down)

`opencoat runtime up` double-forked the daemon at Step 2, so it stays
alive after this terminal closes. **Leave it running** between host-agent
sessions — that's the whole point: concerns and the DCN activation log
persist in `~/.opencoat/*.sqlite` so the next conversation picks up where
this one stopped.

If you really do want to stop it (e.g. freeing port 7878):

```bash
opencoat service stop        # unload LaunchAgent / systemd user unit (keeps files)
opencoat runtime down        # default pid file ~/.opencoat/opencoat.pid
deactivate                   # leave the venv (Step 1b only)
```

To remove autostart entirely: `opencoat service uninstall`.

The PID file is unlinked on a clean exit; if the daemon was
`SIGKILL`'d, delete it manually.

---

## What "Concern" means here

A Concern is the only first-class unit OpenCOAT understands. Every
concern carries:

| field | role |
| --- | --- |
| `id` / `name` / `description` | identity + human label |
| `pointcut` | which joinpoints this concern listens on (+ optional keyword / vector match) |
| `advice` | what to inject when the pointcut fires (`PROMPT_PREFIX`, `TOOL_GUARD`, `MEMORY_WRITE_GUARD`, `RESPONSE_REQUIREMENT`, …) |
| `weaving_policy` | where in the host's COPR to weave (`PROMPT_LEVEL` / `TOOL_LEVEL` / `MEMORY_LEVEL` / `OUTPUT_LEVEL`) and how (`INSERT` / `BLOCK` / `ANNOTATE` / `REPLACE`) |
| `lifecycle_state` | `active` / `pending` / `archived` (driven by the runtime, not by hand) |

Authoring patterns and a recipe gallery live in [concerns.md](concerns.md);
safety rules around `TOOL_GUARD` and `MEMORY_WRITE_GUARD` live in
[rules.md](rules.md).

---

## When to apply this skill

Use this skill when **any** of these are true:

- The user asks to "install OpenCOAT" / "set up the OpenCOAT runtime"
  / "wire concerns into my agent" / **enable daemon autostart** /
  **login or boot persistence** / **fix stub LLM** / **configure API keys
  without pasting them in chat**.
- The user wants a quick reproducible demo of joinpoint / pointcut /
  advice / weaving on top of an existing host agent.
- The user references a `concern.upsert` failure, a missing
  `bootstrap_opencoat.install()` call, or a daemon that won't start
  on `127.0.0.1:7878`.
- The user asks how to add their own concern, edit a pointcut, or
  visualise the Deep Concern Network.

Do **not** use this skill for:

- Generic "agent design" or "prompt engineering" questions unrelated
  to OpenCOAT.
- Collecting or troubleshooting **raw secrets** inside the agent chat
  — redirect to `opencoat configure llm` / local shell instead (see
  [rules.md](rules.md) Rule 8).
- Issues in the upstream `opencoat-runtime-*` Python packages
  themselves — file those at
  <https://github.com/HyperdustLabs/OpenCOAT/issues>.

---

## Compatibility & versions

This skill tracks `opencoat-runtime` major. Today:

| component | min supported | source |
| --- | --- | --- |
| `opencoat-runtime` | `0.1.0` | [PyPI](https://pypi.org/project/opencoat-runtime/) |
| `opencoat-runtime-host` | `0.1.0` | [PyPI](https://pypi.org/project/opencoat-runtime-host/) |
| `opencoat-runtime-protocol` | `0.1.0` | [PyPI](https://pypi.org/project/opencoat-runtime-protocol/) — pulled transitively |

Step 1 installs from PyPI via `pipx`; if you need to embed the runtime
inside a Python application (so its code can `import
opencoat_runtime_host_sdk`), Step 1b uses `pip install` into a regular
venv. Both paths give the same CLI surface.

---

## Troubleshooting (one-liners)

| symptom | likely fix |
| --- | --- |
| `opencoat runtime up` hangs | port 7878 in use → pass `--port 17890` (or another) and re-run `status` with the same flag |
| `opencoat: command not found` | pipx env not on `PATH` → `pipx ensurepath` then reopen the shell, or fall back to Step 1b's venv |
| `opencoat demo` raises `ModuleNotFoundError: opencoat_runtime_host_sdk` | `pipx inject opencoat-runtime opencoat-runtime-host` was skipped — re-run that command |
| `opencoat concern extract` returns `0 candidate(s)` and the banner shows `llm: stub-fallback (degraded — …)` | follow **LLM credentials check** — `opencoat configure llm` in a **local terminal** (never paste keys into chat); restart daemon / service |
| `Client.connect(…)` raises `HostTransportConnectionError` | daemon down or bound on another port; `opencoat runtime status` is the truth |
| `concern.upsert` returns `ValidationError` | concern JSON missing `pointcut.joinpoints` or unknown `AdviceType` — see [concerns.md](concerns.md) |
| `bootstrap_opencoat.install()` does nothing visible | host loop never calls `installed.apply_to(prompt_ctx)` / `installed.guard_tool_call(call)` — see Step 4b for the canonical loop and [concerns.md](concerns.md) for the cookbook |
| daemon refuses to start because PID file exists | stale PID → `rm ~/.opencoat/opencoat.pid && opencoat runtime up …` |
| `opencoat service install` fails on Linux | ensure `systemctl --user` exists; for boot-without-login run `loginctl enable-linger "$USER"` once |
| `opencoat service install` skipped in CI | intentional — only run on a real macOS / Linux user desktop or server |

Anything else: `opencoat inspect joinpoints` and
`opencoat inspect pointcuts` are dependency-free and confirm the
catalogs the runtime is actually using.

---

## Related files in this skill

- [inspection.md](inspection.md) — every read-only command (`concern`,
  `dcn`, `inspect`, `replay`).
- [concerns.md](concerns.md) — authoring patterns + a recipe gallery
  (the 3 demo concerns + 4 useful starters).
- [rules.md](rules.md) — safety rules the host agent must respect
  when OpenCOAT injects `TOOL_GUARD` / `MEMORY_WRITE_GUARD` advice.
