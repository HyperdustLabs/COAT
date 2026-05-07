"""Text → COPR parser."""

from __future__ import annotations

from COAT_runtime_protocol import COPR


class CoprParser:
    def parse(self, raw: str | dict, *, prompt_id: str | None = None) -> COPR:
        """Parse a raw prompt string or messages list into a :class:`COPR`."""
        raise NotImplementedError
