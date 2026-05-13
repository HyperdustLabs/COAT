"""Host adapter port.

Each host (OpenClaw, Hermes, LangGraph, AutoGen, CrewAI, custom) ships its
own adapter that implements this protocol. The runtime stays host-agnostic.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from opencoat_runtime_protocol import ConcernInjection, JoinpointEvent


@runtime_checkable
class HostAdapter(Protocol):
    """Bidirectional adapter: host events → joinpoints, injection → host context."""

    @property
    def host_name(self) -> str: ...

    def map_host_event(self, event: dict) -> JoinpointEvent | None: ...
    def map_host_events(self, events: Iterable[dict]) -> Iterable[JoinpointEvent]: ...
    def apply_injection(self, injection: ConcernInjection, host_context: dict) -> dict: ...
