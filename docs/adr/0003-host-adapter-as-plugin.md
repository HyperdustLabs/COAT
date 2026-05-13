# ADR 0003 — Host adapter as a plugin

## Status

Accepted (v0.2).

## Context

Different agent frameworks (OpenClaw, Hermes, LangGraph, AutoGen,
CrewAI) emit different event vocabularies. We want the runtime core to
stay host-agnostic and not grow `if openclaw: …` branches.

## Decision

Each host ships an *adapter plugin* in
`packages/opencoat-runtime-host/opencoat_runtime_host_<host>/`. The plugin implements
:class:`HostAdapter` (mapping host events → joinpoints, applying
injections back to the host's context) and registers itself via
`pyproject.toml` entrypoints.

The runtime core depends only on the abstract `HostAdapter` protocol
defined in `opencoat_runtime_core.ports.host_adapter`.

## Consequences

- Plugins can be released on their own cadence.
- New hosts only need to fill in `joinpoint_map.py` + `adapter.py` (+
  optional `injector.py` / `tool_guard.py` / `memory_bridge.py` for
  full coverage).
- Users can write a `custom/` adapter in their own repo and load it
  through the plugin discovery mechanism.
