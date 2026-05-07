"""Bridge OpenClaw's memory layer to the DCN — M5."""

from __future__ import annotations


class OpenClawMemoryBridge:
    def sync(self, memory_event: dict) -> None:
        raise NotImplementedError
