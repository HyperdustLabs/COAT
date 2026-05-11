# COAT-runtime-daemon

Long-running runtime process. Composes the core with concrete adapters and
exposes:

- HTTP / JSON-RPC API (M4)
- Unix domain socket (M4)
- Optional gRPC (post-M5)

```bash
COAT-runtime-daemon --config config/default.yaml
```

Layout mirrors v0.2 §4.5.

## `build_runtime` (M4 PR-17)

The factory used by every M4 entrypoint to turn a `DaemonConfig` into a
live `COATRuntime`:

```python
from COAT_runtime_daemon import build_runtime
from COAT_runtime_daemon.config import load_config

with build_runtime(load_config("/etc/coat/daemon.yaml")) as built:
    runtime = built.runtime
    print("llm:", built.llm_label)
    # ... drive runtime.on_joinpoint(...) ...
# Context exit closes sqlite connections; memory backends are no-ops.
```

Supported `storage.{concern,dcn}_store.kind`: `memory` (default), `sqlite`
(path-resolved against the config; `":memory:"` / missing means
ephemeral). Supported `llm.provider`: `stub` (default), `openai`,
`anthropic`, `azure`. Credentials come from the env mapping (defaults to
`os.environ`); model / endpoint / deployment can be pinned in the config
via extra keys (`llm.model`, `llm.deployment`, …).

## JSON-RPC dispatch (M4 PR-18)

In-process JSON-RPC 2.0 over a live `COATRuntime`. Use
:class:`~COAT_runtime_daemon.ipc.http_server.HttpServer` (PR-19) for
HTTP POST, or call :class:`~COAT_runtime_daemon.ipc.jsonrpc_dispatch.JsonRpcHandler`
directly from tests / in-proc wiring.

```python
from COAT_runtime_daemon import build_runtime
from COAT_runtime_daemon.config import load_config
from COAT_runtime_daemon.ipc import JsonRpcHandler

with build_runtime(load_config()) as built:
    rpc = JsonRpcHandler(built.runtime)
    out = rpc.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "health.ping",
        }
    )
    assert out["result"] == {"ok": True}
```

Supported methods today: `health.ping`, `joinpoint.submit`, `concern.*`,
`runtime.snapshot` / `current_vector` / `last_injection`,
`dcn.activation_log`. See `COAT_runtime_daemon.ipc.jsonrpc_dispatch`.

`JsonRpcHandler.handle` returns ``None`` for JSON-RPC **notifications**
(requests with no ``id`` member, per JSON-RPC 2.0 §4.1). The HTTP server
maps ``None`` to ``204 No Content``. Schema validation failures on
``joinpoint`` / ``concern`` payloads surface as ``-32602`` (invalid
params), not ``-32603``.

## Stdlib HTTP JSON-RPC (M4 PR-19)

:class:`~COAT_runtime_daemon.ipc.http_server.HttpServer` wraps
:class:`~COAT_runtime_daemon.ipc.jsonrpc_dispatch.JsonRpcHandler` in a
threading stdlib :class:`http.server.ThreadingHTTPServer`. Only **POST**
to ``path`` (default ``/rpc``) with a JSON body is accepted; **GET**
returns ``405`` with ``Allow: POST``. Bind ``port=0`` for an ephemeral
port in tests.

```python
from COAT_runtime_daemon import build_runtime
from COAT_runtime_daemon.config import load_config
from COAT_runtime_daemon.ipc import HttpServer, JsonRpcHandler

with build_runtime(load_config()) as built:
    rpc = JsonRpcHandler(built.runtime)
    http = HttpServer(rpc, host="127.0.0.1", port=7878)
    http.serve_forever()  # blocks until shutdown() from another thread
```

The legacy name :class:`~COAT_runtime_daemon.ipc.jsonrpc_server.JsonRpcServer`
is an alias of ``HttpServer``. Tests: ``tests/test_http_jsonrpc_server.py``.
