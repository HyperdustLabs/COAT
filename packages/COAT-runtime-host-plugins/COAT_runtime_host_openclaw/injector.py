"""Apply a ConcernInjection back into OpenClaw's context — M5."""

from __future__ import annotations

from COAT_runtime_protocol import ConcernInjection


class OpenClawInjector:
    def apply(self, injection: ConcernInjection, host_context: dict) -> dict:
        raise NotImplementedError
