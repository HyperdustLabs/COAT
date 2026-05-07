"""Meta concern: lifecycle policy (decay rates, archive cutoffs, …)."""

from __future__ import annotations

from COAT_runtime_protocol import Concern


class LifecycleControl:
    def should_archive(self, concern: Concern) -> bool:
        raise NotImplementedError

    def decay_step(self, concern: Concern) -> float:
        raise NotImplementedError
