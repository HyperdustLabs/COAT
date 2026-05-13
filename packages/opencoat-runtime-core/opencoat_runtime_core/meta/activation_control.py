"""Meta concern: gate which concerns may activate this turn."""

from __future__ import annotations

from opencoat_runtime_protocol import Concern, JoinpointEvent


class ActivationControl:
    def allow(self, concern: Concern, joinpoint: JoinpointEvent) -> bool:
        raise NotImplementedError
