# COAT-runtime-host-plugins

First-party host adapters. Each adapter lives in its own importable
sub-package and can be split into a standalone distribution later.

| Adapter | Module | Status |
| --- | --- | --- |
| OpenClaw | `COAT_runtime_host_openclaw` | M5 |
| Hermes | `COAT_runtime_host_hermes` | M7 |
| LangGraph | `COAT_runtime_host_langgraph` | M7 |
| AutoGen | `COAT_runtime_host_autogen` | post-M7 |
| CrewAI | `COAT_runtime_host_crewai` | post-M7 |
| Custom (template) | `COAT_runtime_host_custom` | reference |

Every adapter implements the :class:`COAT_runtime_core.ports.HostAdapter`
protocol and ships a `joinpoint_map.py` that maps host events to joinpoint
names.
