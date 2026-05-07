"""In-process IPC — no transport, direct dispatch (M1)."""

from __future__ import annotations


class InProcServer:
    def serve(self) -> None:
        raise NotImplementedError
