# opencoat-runtime-daemon

Long-running runtime process. Composes the core with concrete adapters and
exposes:

- HTTP / JSON-RPC API (M4)
- Unix domain socket (M4)
- Optional gRPC (post-M5)

```bash
opencoat-daemon --config config/default.yaml
```

Layout mirrors v0.2 §4.5.

## `build_runtime` (M4 PR-17)

The factory used by every M4 entrypoint to turn a `DaemonConfig` into a
live `OpenCOATRuntime`:

```python
from opencoat_runtime_daemon import build_runtime
from opencoat_runtime_daemon.config import load_config

with build_runtime(load_config("/etc/opencoat/daemon.yaml")) as built:
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

In-process JSON-RPC 2.0 over a live `OpenCOATRuntime`. Use
:class:`~opencoat_runtime_daemon.ipc.http_server.HttpServer` (PR-19) for
HTTP POST, or call :class:`~opencoat_runtime_daemon.ipc.jsonrpc_dispatch.JsonRpcHandler`
directly from tests / in-proc wiring.

```python
from opencoat_runtime_daemon import build_runtime
from opencoat_runtime_daemon.config import load_config
from opencoat_runtime_daemon.ipc import JsonRpcHandler

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
`dcn.activation_log`. See `opencoat_runtime_daemon.ipc.jsonrpc_dispatch`.

`JsonRpcHandler.handle` returns ``None`` for JSON-RPC **notifications**
(requests with no ``id`` member, per JSON-RPC 2.0 §4.1). The HTTP server
maps ``None`` to ``204 No Content``. Schema validation failures on
``joinpoint`` / ``concern`` payloads surface as ``-32602`` (invalid
params), not ``-32603``.

## Stdlib HTTP JSON-RPC (M4 PR-19)

:class:`~opencoat_runtime_daemon.ipc.http_server.HttpServer` wraps
:class:`~opencoat_runtime_daemon.ipc.jsonrpc_dispatch.JsonRpcHandler` in a
threading stdlib :class:`http.server.ThreadingHTTPServer`. Only **POST**
to ``path`` (default ``/rpc``) with a JSON body is accepted; **GET**
returns ``405`` with ``Allow: POST``. Bind ``port=0`` for an ephemeral
port in tests.

```python
from opencoat_runtime_daemon import build_runtime
from opencoat_runtime_daemon.config import load_config
from opencoat_runtime_daemon.ipc import HttpServer, JsonRpcHandler

with build_runtime(load_config()) as built:
    rpc = JsonRpcHandler(built.runtime)
    http = HttpServer(rpc, host="127.0.0.1", port=7878)
    http.serve_forever()  # blocks until shutdown() from another thread
```

The legacy name :class:`~opencoat_runtime_daemon.ipc.jsonrpc_server.JsonRpcServer`
is an alias of ``HttpServer``. Tests: ``tests/test_http_jsonrpc_server.py``.

## Daemon lifecycle (M4 PR-20)

`Daemon` composes `build_runtime` + `JsonRpcHandler` + `HttpServer`
with PID-file management and signal-driven shutdown:

```python
from opencoat_runtime_daemon import Daemon
from opencoat_runtime_daemon.config import load_config

cfg = load_config()
cfg.ipc.http.enabled = True  # start HTTP listener
with Daemon(cfg, pid_file="/run/opencoat.pid") as d:
    # d.runtime_handler is a live JsonRpcHandler;
    # d.http_server exposes host/port/path when ipc.http.enabled.
    d.wait()  # blocks until d.stop()
```

For long-running processes, `run_until_signal()` installs `SIGTERM` /
`SIGINT` handlers on the main thread and drains gracefully:

```bash
python -m opencoat_runtime_daemon --config /etc/opencoat/daemon.yaml --pid-file /run/opencoat.pid
```

`Daemon.reload()` swaps the runtime in place — old sqlite connections
are closed, the listening socket stays up, and new requests pick up
the rebuilt `OpenCOATRuntime` on entry. The PID file (`PidFile`) is
created exclusively (`O_EXCL`), replaces stale entries whose recorded
PID is no longer alive, and is removed on stop only if it still
contains our own PID. Tests: `tests/test_pidfile.py` and
`tests/test_daemon_lifecycle.py`.

The CLI driver — `COATr runtime up | down | status` — lives in
`opencoat-runtime-cli` (M4 PR-21) and double-forks this daemon so it is
owned by `init` rather than the calling shell.
