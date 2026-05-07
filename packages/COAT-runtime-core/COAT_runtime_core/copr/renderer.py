"""COPR → text renderer (round-trips back to a plain prompt string)."""

from __future__ import annotations

from COAT_runtime_protocol import COPR


class CoprRenderer:
    def render(self, copr: COPR) -> str:
        raise NotImplementedError
