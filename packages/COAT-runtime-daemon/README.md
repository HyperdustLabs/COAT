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
