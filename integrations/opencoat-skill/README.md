# opencoat-skill (monorepo mirror)

This directory is the **canonical working copy** of
[`HyperdustLabs/opencoat-skill`](https://github.com/HyperdustLabs/opencoat-skill)
inside the OpenCOAT repo. Edit here first, then open a PR on the skill repo
and redeploy the `www.opencoat.ai` worker (see upstream `DEPLOY.md`) so CDN
URLs stay in sync.

---

# opencoat-skill

The 5-minute install skill for [OpenCOAT](https://github.com/HyperdustLabs/OpenCOAT) —
the Open Concern-Oriented Agent Thinking Runtime.

Drop this skill into any agent that supports the agent-skill
convention (Cursor, Claude Code, Codex, …). The **entire** host→agent
instruction can be a single line (see `SKILL.md` §Canonical host prompt); all
requirements for the agent live in `SKILL.md` and linked files. The skill tells
the agent how to:

- install `opencoat-runtime` from
  [PyPI](https://pypi.org/project/opencoat-runtime/) — one
  `pipx install opencoat-runtime` puts the `opencoat` CLI on `PATH`,
  and `pipx inject opencoat-runtime opencoat-runtime-host` wires the
  host SDK into the same env so the demo's lazy imports succeed
  (`opencoat-runtime-protocol` comes along transitively),
- start a local daemon (zero-config HTTP on `127.0.0.1:7878/rpc`) and register **OS autostart** via `opencoat service install`,
- import three dramatic demo concerns,
- close the full loop with one command — `opencoat demo` fires three
  events through `install_hooks` and uses the pickup API
  (`apply_to` / `guard_tool_call`) to fold the resulting advice
  back into a tiny in-script host. Three scenes print BEFORE /
  AFTER so users see concerns visibly change behavior on first
  read. `opencoat demo --in-proc` runs the same tour without a
  daemon (no setup), and `opencoat demo --script-out demo_host.py`
  dumps the equivalent Python for users who want a template to
  adapt for a real host. Scaffold an OpenClaw plugin with
  `opencoat plugin install openclaw` for the same loop pre-wired,
  then
- inspect the resulting Deep Concern Network.

## Layout

```text
opencoat-skill/
├── SKILL.md                       # main instructions (≤500 lines)
├── skill.json                     # manifest
├── inspection.md                  # read-only inspection commands
├── concerns.md                    # authoring patterns + recipe gallery
├── rules.md                       # safety rules the host must respect
├── bootstrap_daemon.sh            # post-pipx: runtime up + service install
├── DEPLOY.md                      # one-time CF Worker + DNS setup
├── worker/                        # Cloudflare Worker source (deploys via CI)
├── LICENSE                        # Apache-2.0
└── .github/workflows/
    ├── verify.yml                 # CI: parse skill.json + link integrity
    └── deploy-worker.yml          # CI: redeploy worker on skill / worker push
```

## Install (per-agent)

| Agent | Path |
| --- | --- |
| Cursor (personal) | `~/.cursor/skills/opencoat/` |
| Cursor (project) | `<repo>/.cursor/skills/opencoat/` |
| Claude Code | `~/.claude/skills/opencoat/` |
| Codex | `~/.codex/skills/opencoat/` |

Three install paths, pick whichever fits the agent:

1. **Self-install from the website** — point the agent at
   `https://www.opencoat.ai/SKILL.md` and tell it to "read the skill
   and follow the install instructions". The agent fetches all five
   skill files (`SKILL.md`, `concerns.md`, `inspection.md`,
   `rules.md`, `skill.json`) from `https://www.opencoat.ai/<file>`,
   drops them into its skills directory, then walks the user
   through the runtime install. This is the most "Moltbook-shaped"
   path and the one the website is optimized for. The Cloudflare
   Worker + DNS setup that powers these URLs is documented in
   [`DEPLOY.md`](DEPLOY.md) — once for the maintainer, never for
   the user.
2. **Clone the repo** into the agent path above. Useful if you want
   to track skill changes with `git pull`.
3. **Skill installer** — if your agent has a built-in skill
   installer (Cursor, Codex), point it at this repo URL.

## Versioning

This skill tracks the major version of `opencoat-runtime` (which ships
the daemon + the `opencoat` CLI in one wheel as of 0.1.0). See
[`skill.json`](skill.json) `compatible_with` for the exact minimum
versions of each upstream package.

## Issues

- Skill content / phrasing / wiring → file here.
- Upstream runtime bugs → file at
  <https://github.com/HyperdustLabs/OpenCOAT/issues>.

## License

Apache-2.0. See [LICENSE](LICENSE).
