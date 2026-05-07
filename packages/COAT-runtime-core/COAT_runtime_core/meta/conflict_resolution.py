"""Meta concern: how to resolve detected conflicts."""

from __future__ import annotations

from COAT_runtime_protocol import Concern


class ConflictResolution:
    def pick_winner(self, a: Concern, b: Concern) -> Concern:
        raise NotImplementedError
