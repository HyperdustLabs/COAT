"""Stdlib HTTP server mounting :class:`JsonRpcHandler` (M4 PR-19).

POST JSON-RPC requests to a single path (default ``/rpc``). Successful
RPC responses return ``200`` with ``application/json``. JSON-RPC
notifications (no ``id`` in the request) yield ``204 No Content`` with an
empty body, per JSON-RPC 2.0 §4.1.
"""

from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from .jsonrpc_dispatch import JsonRpcHandler

# Reject absurdly large bodies before buffering into memory.
_MAX_BODY_BYTES = 8 * 1024 * 1024


def _normalize_path(path: str) -> str:
    """Strip query/fragment and trailing slash (except root)."""
    p = urlparse(path).path
    if not p.startswith("/"):
        p = "/" + p
    if len(p) > 1:
        p = p.rstrip("/")
    return p or "/"


class _JsonRpcHttpRequestHandler(BaseHTTPRequestHandler):
    """One-shot POST handler; ``ThreadingHTTPServer`` carries ``coat_*`` attrs."""

    protocol_version = "HTTP/1.1"

    def log_message(self, _format: str, *_args: object) -> None:
        # Silence default stderr logging — callers can wrap with logging later.
        return

    def do_POST(self) -> None:
        server = self.server
        rpc_path = server.coat_rpc_path  # type: ignore[attr-defined]
        handler: JsonRpcHandler = server.coat_rpc_handler  # type: ignore[attr-defined]

        req_path = _normalize_path(self.path)
        if req_path != rpc_path:
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
            return

        raw_len = self.headers.get("Content-Length")
        try:
            length = 0 if raw_len is None else int(raw_len)
        except ValueError:
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid Content-Length")
            return
        if length < 0:
            self.send_error(HTTPStatus.BAD_REQUEST, "Negative Content-Length")
            return
        if length > _MAX_BODY_BYTES:
            self.send_error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Body too large")
            return

        body = self.rfile.read(length)
        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError:
            self.send_error(HTTPStatus.BAD_REQUEST, "Body must be UTF-8")
            return

        try:
            out = handler.handle(text)
        except Exception as exc:  # pragma: no cover — JsonRpcHandler should not raise
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))
            return

        if out is None:
            # JSON-RPC notification — no response object (§4.1).
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
            return

        payload = json.dumps(out, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        server = self.server
        rpc_path = server.coat_rpc_path  # type: ignore[attr-defined]
        req_path = _normalize_path(self.path)
        if req_path == rpc_path:
            body = b"Use POST with a JSON-RPC 2.0 body\n"
            self.send_response(HTTPStatus.METHOD_NOT_ALLOWED)
            self.send_header("Allow", "POST")
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not Found")


class _CoatJsonRpcHTTPServer(ThreadingHTTPServer):
    """Binds :class:`JsonRpcHandler` onto ``coat_rpc_*`` server attributes."""

    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        rpc_handler: JsonRpcHandler,
        rpc_path: str,
    ) -> None:
        self.coat_rpc_handler = rpc_handler
        self.coat_rpc_path = _normalize_path(rpc_path)
        super().__init__(server_address, _JsonRpcHttpRequestHandler)


class HttpServer:
    """Threading stdlib HTTP server exposing JSON-RPC POST at ``path``."""

    def __init__(
        self,
        rpc_handler: JsonRpcHandler,
        *,
        host: str = "127.0.0.1",
        port: int = 7878,
        path: str = "/rpc",
    ) -> None:
        self._host = host
        self._path = path
        self._httpd = _CoatJsonRpcHTTPServer((host, port), rpc_handler, path)
        self._started = False

    @property
    def host(self) -> str:
        return self._host

    @property
    def port(self) -> int:
        """Actual bound port (useful when ``port`` was ``0``)."""
        return self._httpd.server_address[1]

    @property
    def path(self) -> str:
        return self._path

    def serve_forever(self, poll_interval: float = 0.5) -> None:
        """Block the current thread serving HTTP until :meth:`shutdown`."""
        self._started = True
        self._httpd.serve_forever(poll_interval=poll_interval)

    def shutdown(self) -> None:
        """Stop :meth:`serve_forever` (safe from another thread)."""
        self._httpd.shutdown()

    def replace_handler(self, rpc_handler: JsonRpcHandler) -> None:
        """Swap the mounted :class:`JsonRpcHandler` (thread-safe).

        Each request reads ``coat_rpc_handler`` off the server on entry,
        so an atomic attribute swap is enough — no socket restart.
        Used by :meth:`opencoat_runtime_daemon.daemon.Daemon.reload`.
        """
        self._httpd.coat_rpc_handler = rpc_handler

    def server_close(self) -> None:
        """Release the listening socket."""
        self._httpd.server_close()

    def __enter__(self) -> HttpServer:
        return self

    def __exit__(self, *exc: object) -> None:
        if self._started:
            self.shutdown()
        self.server_close()
