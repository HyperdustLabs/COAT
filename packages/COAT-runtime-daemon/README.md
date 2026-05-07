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
