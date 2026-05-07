"""CrewAI adapter — post-M7 milestone."""

from __future__ import annotations

from collections.abc import Iterable

from COAT_runtime_core.ports import HostAdapter
from COAT_runtime_protocol import ConcernInjection, JoinpointEvent


class CrewAIAdapter(HostAdapter):
    @property
    def host_name(self) -> str:
        return "crewai"

    def map_host_event(self, event: dict) -> JoinpointEvent | None:
        raise NotImplementedError

    def map_host_events(self, events: Iterable[dict]) -> Iterable[JoinpointEvent]:
        for event in events:
            jp = self.map_host_event(event)
            if jp is not None:
                yield jp

    def apply_injection(self, injection: ConcernInjection, host_context: dict) -> dict:
        raise NotImplementedError
