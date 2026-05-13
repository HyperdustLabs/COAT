"""POST /v1/joinpoint — push a joinpoint, return an injection."""

from __future__ import annotations

from opencoat_runtime_protocol import ConcernInjection, JoinpointEvent


class JoinpointAPI:
    def submit(self, jp: JoinpointEvent) -> ConcernInjection | None:
        raise NotImplementedError
