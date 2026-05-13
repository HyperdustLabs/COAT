"""Reference template for a user-defined host adapter.

Replace ``host_name``, fill in :meth:`map_host_event` to translate your
agent framework's events into :class:`JoinpointEvent` instances, and
implement :meth:`apply_injection` to fold the runtime's advice back into
your context.

Mapping policy:

* lifecycle events (request received, before LLM, after LLM, …) → the
  matching name in :class:`opencoat_runtime_core.joinpoint.JOINPOINT_CATALOG`
* messages → :class:`MessagePayload` with the right ``role``
* tool calls → :class:`StructureFieldPayload` with ``tool_call.arguments.*``
"""

from __future__ import annotations

from collections.abc import Iterable

from opencoat_runtime_core.ports import HostAdapter
from opencoat_runtime_protocol import ConcernInjection, JoinpointEvent


class CustomAdapter(HostAdapter):
    def __init__(self, host_name: str = "custom") -> None:
        self._host_name = host_name

    @property
    def host_name(self) -> str:
        return self._host_name

    def map_host_event(self, event: dict) -> JoinpointEvent | None:
        raise NotImplementedError("Override this in your subclass.")

    def map_host_events(self, events: Iterable[dict]) -> Iterable[JoinpointEvent]:
        for event in events:
            jp = self.map_host_event(event)
            if jp is not None:
                yield jp

    def apply_injection(self, injection: ConcernInjection, host_context: dict) -> dict:
        raise NotImplementedError("Override this in your subclass.")
