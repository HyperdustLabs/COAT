"""Meta concern: gate which sources may produce concerns."""

from __future__ import annotations

from opencoat_runtime_protocol import Concern


class ExtractionControl:
    def allow(self, candidate: Concern) -> bool:
        raise NotImplementedError

    def downgrade(self, candidate: Concern, *, reason: str) -> Concern:
        raise NotImplementedError
