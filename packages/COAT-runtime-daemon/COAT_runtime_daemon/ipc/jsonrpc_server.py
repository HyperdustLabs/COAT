"""JSON-RPC over HTTP — alias of :class:`~COAT_runtime_daemon.ipc.http_server.HttpServer` (M4 PR-19)."""

from __future__ import annotations

from .http_server import HttpServer as JsonRpcServer

__all__ = ["JsonRpcServer"]
