"""HTTP / JSON-RPC server — M4."""

from __future__ import annotations


class HttpServer:
    def __init__(self, *, host: str = "127.0.0.1", port: int = 7878) -> None:
        self._host = host
        self._port = port

    def serve(self) -> None:
        raise NotImplementedError
