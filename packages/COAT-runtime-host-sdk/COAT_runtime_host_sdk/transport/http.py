"""HTTP / JSON-RPC transport — M4 milestone."""

from __future__ import annotations

from COAT_runtime_protocol import ConcernInjection, JoinpointEvent


class HttpTransport:
    def __init__(self, *, base_url: str, timeout_seconds: float = 5.0) -> None:
        self._base_url = base_url
        self._timeout = timeout_seconds

    def emit(self, joinpoint: JoinpointEvent) -> ConcernInjection | None:
        raise NotImplementedError
