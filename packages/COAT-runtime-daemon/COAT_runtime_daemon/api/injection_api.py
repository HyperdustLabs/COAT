"""GET /v1/injection/{turn_id} — replay the injection produced for a turn."""

from __future__ import annotations

from COAT_runtime_protocol import ConcernInjection


class InjectionAPI:
    def get(self, turn_id: str) -> ConcernInjection | None:
        raise NotImplementedError
