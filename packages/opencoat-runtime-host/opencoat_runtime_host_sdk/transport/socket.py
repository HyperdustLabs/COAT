"""Unix domain socket transport — M4 milestone."""

from __future__ import annotations

from opencoat_runtime_protocol import ConcernInjection, JoinpointEvent


class SocketTransport:
    def __init__(self, *, path: str) -> None:
        self._path = path

    def emit(self, joinpoint: JoinpointEvent) -> ConcernInjection | None:
        raise NotImplementedError
