"""Meta concern: which concerns must be verified each turn."""

from __future__ import annotations

from COAT_runtime_protocol import Concern


class VerificationControl:
    def select(self, active: list[Concern]) -> list[Concern]:
        raise NotImplementedError
