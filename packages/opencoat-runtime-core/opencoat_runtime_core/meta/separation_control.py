"""Meta concern: drive split / merge / rewrite decisions in the separator."""

from __future__ import annotations


class SeparationControl:
    def should_split(self, concern_id: str) -> bool:
        raise NotImplementedError

    def should_merge(self, a_id: str, b_id: str) -> bool:
        raise NotImplementedError
