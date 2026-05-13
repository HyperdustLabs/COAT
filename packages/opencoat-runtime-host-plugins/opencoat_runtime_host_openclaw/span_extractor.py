"""Derive COPR spans from an OpenClaw ``message`` dict (M5 #29).

OpenClaw messages are untyped JSON blobs in practice. This extractor
accepts the common shapes the rest of the OpenCOAT examples already use
(``text`` / ``raw_text`` / ``content``) and emits zero or one
:class:`~opencoat_runtime_protocol.envelopes.CoprSpan` so downstream COPR
machinery can attach pointcuts without importing OpenClaw itself.

* **id** — ``message["id"]`` whenever the key is present and not
  ``None`` (including falsy values like integer ``0`` or empty string),
  otherwise a fresh UUID4 string. This preserves correlation for hosts
  that emit zero-indexed integer IDs (Codex P2 on PR #29).
* **text** — first non-empty among ``text``, ``raw_text``, ``content``.
* **semantic_type** — ``message["role"]`` when present, else
  ``"openclaw.message"``.
"""

from __future__ import annotations

import uuid
from typing import Any

from opencoat_runtime_protocol.envelopes import CoprSpan


class OpenClawSpanExtractor:
    """Map a host message dict → :class:`CoprSpan` list."""

    def extract(self, message: dict[str, Any]) -> list[CoprSpan]:
        text = _first_text(message)
        if text is None:
            return []
        raw_id = message.get("id")
        # Preserve falsy-but-present IDs (e.g. integer 0) rather than
        # rolling a UUID — only fall back when the key is missing/None.
        span_id = str(raw_id) if raw_id is not None else str(uuid.uuid4())
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
