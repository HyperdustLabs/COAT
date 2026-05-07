"""Concern deduplication — collapses ``duplicates`` relations."""

from __future__ import annotations

from COAT_runtime_protocol import Concern


class Dedupe:
    def collapse(self, concerns: list[Concern]) -> list[Concern]:
        raise NotImplementedError
