"""JSON-RPC dispatcher (mounted under HTTP)."""

from __future__ import annotations


class JsonRpcServer:
    def serve(self) -> None:
        raise NotImplementedError
