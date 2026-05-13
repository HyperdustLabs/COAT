"""Stdlib HTTP JSON-RPC client for the OpenCOAT daemon (M4 PR-21).

A tiny synchronous client that POSTs JSON-RPC 2.0 requests to a running
:class:`~opencoat_runtime_daemon.ipc.http_server.HttpServer`. Only stdlib —
``http.client`` + ``json`` + ``socket`` — so the CLI stays free of
runtime dependencies on httpx/requests.

Errors map cleanly so callers can branch on transport vs RPC failure:

* :class:`HttpRpcConnectionError` — the daemon isn't listening (refused,
  timeout, DNS, etc.). Used by ``COATr runtime status`` to say *stopped*
  instead of crashing.
* :class:`HttpRpcProtocolError` — the daemon responded but with the
  wrong shape (non-2xx, non-JSON body, missing ``jsonrpc``).
* :class:`HttpRpcCallError` — the daemon returned a JSON-RPC ``error``
  object. Exposes ``code`` and ``message`` from §5.1 of the spec.
"""

from __future__ import annotations

import json
import socket
from http.client import HTTPConnection, HTTPException
from typing import Any

_DEFAULT_TIMEOUT_SECONDS = 5.0


class HttpRpcError(RuntimeError):
    """Base for all client-side RPC failures."""


class HttpRpcConnectionError(HttpRpcError):
    """The daemon is not reachable (ECONNREFUSED, timeout, DNS, …)."""


class HttpRpcProtocolError(HttpRpcError):
    """The daemon answered, but the response shape is invalid."""


class HttpRpcCallError(HttpRpcError):
    """The daemon returned a JSON-RPC ``error`` object (§5.1)."""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(f"JSON-RPC error {code}: {message}")
        self.code = code
        self.message = message
        self.data = data


class HttpRpcClient:
    """Synchronous HTTP JSON-RPC 2.0 client.

    Threading: each :meth:`call` opens and closes a fresh
    :class:`http.client.HTTPConnection`, so instances are safe to share
    across threads even though individual connections are not.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 7878,
        path: str = "/rpc",
        *,
        timeout: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._host = host
        self._port = int(port)
        self._path = path if path.startswith("/") else "/" + path
        self._timeout = float(timeout)
        self._next_id = 1

    @property
    def host(self) -> str:
        return self._host

    @property
    def port(self) -> int:
        return self._port

    @property
    def path(self) -> str:
        return self._path

    @property
    def endpoint(self) -> str:
        return f"http://{self._host}:{self._port}{self._path}"

    def call(
        self,
        method: str,
        params: dict[str, Any] | list[Any] | None = None,
        *,
        request_id: int | str | None = None,
    ) -> Any:
        """Send a JSON-RPC request and return the ``result`` field.

        Raises one of the :class:`HttpRpcError` subclasses on failure.
        """
        if not isinstance(method, str) or not method:
            raise ValueError("method must be a non-empty string")
        if request_id is None:
            request_id = self._next_id
            self._next_id += 1
        body: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            body["params"] = params
        payload = json.dumps(body, separators=(",", ":")).encode("utf-8")

        conn = HTTPConnection(self._host, self._port, timeout=self._timeout)
        try:
            try:
                conn.request(
                    "POST",
                    self._path,
                    body=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Content-Length": str(len(payload)),
                        "Accept": "application/json",
                    },
                )
                resp = conn.getresponse()
                raw = resp.read()
                status = resp.status
            except (ConnectionRefusedError, TimeoutError, socket.gaierror, OSError) as exc:
                # OSError covers EHOSTUNREACH / ENETUNREACH / "connection
                # reset" — anything that signals the daemon is not there.
                raise HttpRpcConnectionError(f"could not reach {self.endpoint}: {exc}") from exc
            except HTTPException as exc:
                raise HttpRpcProtocolError(f"HTTP protocol error: {exc}") from exc
        finally:
            conn.close()

        if status == 204:
            # Notification — should not happen for id-bearing requests,
            # but treat it as a benign None.
            return None
        if status != 200:
            raise HttpRpcProtocolError(
                f"unexpected HTTP {status} from {self.endpoint}: {raw[:200]!r}"
            )
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HttpRpcProtocolError(f"non-JSON response from {self.endpoint}: {exc}") from exc
        if not isinstance(data, dict) or data.get("jsonrpc") != "2.0":
            raise HttpRpcProtocolError(f"not a JSON-RPC 2.0 response: {data!r}")

        if "error" in data:
            err = data["error"] or {}
            if not isinstance(err, dict):
                raise HttpRpcProtocolError(f"malformed error object: {err!r}")
            raise HttpRpcCallError(
                code=int(err.get("code", -32603)),
                message=str(err.get("message", "")),
                data=err.get("data"),
            )
        return data.get("result")


__all__ = [
    "HttpRpcCallError",
    "HttpRpcClient",
    "HttpRpcConnectionError",
    "HttpRpcError",
    "HttpRpcProtocolError",
]
