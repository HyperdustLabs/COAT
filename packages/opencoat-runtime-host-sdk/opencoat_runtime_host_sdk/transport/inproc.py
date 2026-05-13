"""In-process transport — direct function call, zero serialization."""

from __future__ import annotations

from typing import Any

from opencoat_runtime_protocol import ConcernInjection, JoinpointEvent


class InProcTransport:
    def __init__(self, runtime: Any) -> None:
        self._runtime = runtime

    def emit(self, joinpoint: JoinpointEvent) -> ConcernInjection | None:
        raise NotImplementedError
