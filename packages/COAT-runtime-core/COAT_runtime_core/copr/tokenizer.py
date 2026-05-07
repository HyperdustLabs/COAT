"""Lightweight tokenizer for COPR.

We deliberately do NOT pull in a heavy LLM tokenizer dependency in M0 —
the default is a whitespace + punctuation splitter; concrete adapters
(e.g. tiktoken) plug in at higher milestones.
"""

from __future__ import annotations


class CoprTokenizer:
    def tokenize(self, text: str) -> list[str]:
        raise NotImplementedError

    def count_tokens(self, text: str) -> int:
        raise NotImplementedError
