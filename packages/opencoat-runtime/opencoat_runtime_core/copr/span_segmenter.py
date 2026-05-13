"""Span segmenter — slice messages into semantic spans (claims, instructions, …)."""

from __future__ import annotations

from opencoat_runtime_protocol.envelopes import CoprSpan


class SpanSegmenter:
    def segment(self, raw_text: str) -> list[CoprSpan]:
        raise NotImplementedError
