"""Turn Loop — synchronous, returns a :class:`ConcernInjection`.

Sequence (v0.1 §22.1):

    user input
        → joinpoint detection
        → concern extraction
        → pointcut matching
        → concern activation
        → advice weaving
        → host response
        → concern verification
        → lifecycle update
"""

from __future__ import annotations

from COAT_runtime_protocol import ConcernInjection, JoinpointEvent


class TurnLoop:
    def run(self, joinpoint: JoinpointEvent) -> ConcernInjection | None:
        raise NotImplementedError
