# opencoat-runtime-host-sdk

Host-side SDK. Lets a host (OpenClaw, LangGraph, custom) emit joinpoints and
consume injections without coupling to the runtime's internals.

```python
from opencoat_runtime_host_sdk import Client, joinpoint

client = Client.connect("unix:///run/COATr.sock")

@joinpoint("before_response", client=client)
def generate_response(ctx): ...
```

Transports: `inproc`, `socket`, `http`. M0 ships skeleton classes; M4 wires
the HTTP transport against the daemon.
