"""Apply a :class:`ConcernInjection` to a host context."""

from __future__ import annotations

from opencoat_runtime_protocol import ConcernInjection


class InjectionConsumer:
    def consume(self, injection: ConcernInjection, host_context: dict) -> dict:
        """Merge the injection into ``host_context`` and return the new context."""
        raise NotImplementedError
