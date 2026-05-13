# opencoat-runtime-host

Host-side integration for the OpenCOAT Runtime — the library you embed inside an
agent framework so it can emit joinpoints to OpenCOAT and consume concern
injections back.

This package ships:

| Module                                | Role                                                              |
| ------------------------------------- | ----------------------------------------------------------------- |
| `opencoat_runtime_host_sdk`           | joinpoint emitter, injection consumer, transports (inproc, socket, http) |
| `opencoat_runtime_host_openclaw`      | OpenClaw adapter (events, tool guard, memory bridge, install hooks) |
| `opencoat_runtime_host_hermes`        | Hermes adapter                                                    |
| `opencoat_runtime_host_langgraph`     | LangGraph adapter                                                 |
| `opencoat_runtime_host_autogen`       | AutoGen adapter                                                   |
| `opencoat_runtime_host_crewai`        | CrewAI adapter                                                    |
| `opencoat_runtime_host_custom`        | scaffold for a fully custom host                                  |

Only depends on [`opencoat-runtime-protocol`](https://pypi.org/project/opencoat-runtime-protocol/) — the runtime daemon you talk to lives in [`opencoat-runtime`](https://pypi.org/project/opencoat-runtime/).

## Install

```bash
pip install "opencoat-runtime-host[openclaw]"
pip install "opencoat-runtime-host[langgraph]"   # pulls langgraph itself
pip install "opencoat-runtime-host[hermes,autogen,crewai]"
pip install "opencoat-runtime-host[http]"        # SDK with httpx transport
```

## Quick start

```python
from opencoat_runtime_host_sdk import Client, joinpoint

client = Client.from_env()          # picks transport from OPENCOAT_TRANSPORT

@joinpoint("before_response", client=client, level=1)
def generate(ctx: dict) -> str:
    return llm.complete(ctx["prompt"])
```

For framework-specific adapters see the per-module READMEs and
<https://github.com/HyperdustLabs/OpenCOAT/tree/main/docs>.

## License

Apache-2.0.
