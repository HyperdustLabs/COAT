"""Unix domain socket IPC server — M4."""

from __future__ import annotations


class SocketServer:
    def __init__(self, *, path: str) -> None:
        self._path = path

    def serve(self) -> None:
        raise NotImplementedError
