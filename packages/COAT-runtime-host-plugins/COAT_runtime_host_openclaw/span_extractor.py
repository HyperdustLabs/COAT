"""OpenClaw message → COPR span extractor — M5."""

from __future__ import annotations

from COAT_runtime_protocol.envelopes import CoprSpan


class OpenClawSpanExtractor:
    def extract(self, message: dict) -> list[CoprSpan]:
        raise NotImplementedError
