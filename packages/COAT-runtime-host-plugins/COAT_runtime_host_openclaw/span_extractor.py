"""Derive COPR spans from an OpenClaw ``message`` dict (M5 #29).

OpenClaw messages are untyped JSON blobs in practice. This extractor
accepts the common shapes the rest of the COAT examples already use
(``text`` / ``raw_text`` / ``content``) and emits zero or one
:class:`~COAT_runtime_protocol.envelopes.CoprSpan` so downstream COPR
machinery can attach pointcuts without importing OpenClaw itself.

* **id** — ``message["id"]`` when present, otherwise a fresh UUID4 string.
* **text** — first non-empty among ``text``, ``raw_text``, ``content``.
* **semantic_type** — ``message["role"]`` when present, else
  ``"openclaw.message"``.
"""

from __future__ import annotations

import uuid
from typing import Any

from COAT_runtime_protocol.envelopes import CoprSpan


class OpenClawSpanExtractor:
    """Map a host message dict → :class:`CoprSpan` list."""

    def extract(self, message: dict[str, Any]) -> list[CoprSpan]:
        text = _first_text(message)
        if text is None:
            return []
        span_id = str(message["id"]) if message.get("id") else str(uuid.uuid4())
        role = message.get("role")
        semantic = str(role) if role is not None else "openclaw.message"
        return [CoprSpan(id=span_id, text=text, semantic_type=semantic)]


def _first_text(message: dict[str, Any]) -> str | None:
    for key in ("text", "raw_text", "content"):
        raw = message.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw
    return None


__all__ = ["OpenClawSpanExtractor"]
