"""HTTP / JSON-RPC transport for the host SDK.

Submits joinpoint events to a running OpenCOAT daemon over HTTP
JSON-RPC 2.0 (the same wire surface as the CLI's ``HttpRpcClient``).
Stdlib-only — ``http.client`` + ``json`` — so the host SDK stays free
of runtime dependencies on ``httpx`` / ``requests``.

Wire shape mirrors :mod:`opencoat_runtime_daemon.ipc.jsonrpc_dispatch`:

* Method: ``joinpoint.submit``
* Params: ``{"joinpoint": <JoinpointEvent>, "return_none_when_empty"?, "context"?}``
* Result: ``ConcernInjection`` wire object, or ``null``

Errors raise typed subclasses of :class:`HostTransportError` so host
code can branch on "daemon stopped" vs "daemon answered with an error":

* :class:`HostTransportConnectionError` — daemon unreachable (refused,
  timeout, DNS).
* :class:`HostTransportProtocolError`   — daemon answered, wrong shape
  (non-2xx, non-JSON, missing ``jsonrpc``).
* :class:`HostTransportCallError`       — daemon returned a JSON-RPC
  ``error`` object (§5.1).
"""

from __future__ import annotations

import json
import socket
from http.client import HTTPConnection, HTTPException
from typing import Any
from urllib.parse import urlparse

from opencoat_runtime_protocol import ConcernInjection, JoinpointEvent

_DEFAULT_TIMEOUT_SECONDS = 5.0


class HostTransportError(RuntimeError):
    """Base class for all HTTP transport failures."""


class HostTransportConnectionError(HostTransportError):
    """The daemon is not reachable."""


class HostTransportProtocolError(HostTransportError):
    """The daemon answered, but the response shape is invalid."""


class HostTransportCallError(HostTransportError):
    """The daemon returned a JSON-RPC ``error`` object (§5.1)."""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(f"JSON-RPC error {code}: {message}")
        self.code = code
        self.message = message
        self.data = data


class HttpTransport:
    """Submit joinpoints to a daemon at ``base_url`` over HTTP JSON-RPC."""

    def __init__(
        self,
        *,
        base_url: str,
        path: str = "/rpc",
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"HttpTransport base_url must be http(s)://…, got {base_url!r}")
        if not parsed.hostname:
            raise ValueError(f"HttpTransport base_url is missing a host: {base_url!r}")
        self._host = parsed.hostname
        self._port = parsed.port or (443 if parsed.scheme == "https" else 80)
        # If the user passed a base_url with a path component (e.g.
        # http://host:port/v1/opencoat), use that as the RPC path and
        # ignore the explicit ``path=`` kwarg. Otherwise use ``path``.
        url_path = parsed.path.rstrip("/")
        if url_path:
            self._rpc_path = url_path
        else:
            self._rpc_path = path if path.startswith("/") else "/" + path
        self._scheme = parsed.scheme
        self._timeout = float(timeout_seconds)
        self._next_id = 1

    @property
    def endpoint(self) -> str:
        return f"{self._scheme}://{self._host}:{self._port}{self._rpc_path}"

    def emit(
        self,
        joinpoint: JoinpointEvent,
        *,
        context: dict[str, Any] | None = None,
        return_none_when_empty: bool = False,
    ) -> ConcernInjection | None:
        params: dict[str, Any] = {"joinpoint": joinpoint.model_dump(mode="json")}
        if context is not None:
            params["context"] = context
        if return_none_when_empty:
            params["return_none_when_empty"] = True

        raw = self._call("joinpoint.submit", params)
        if raw is None:
            return None
        return ConcernInjection.model_validate(raw)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _call(self, method: str, params: dict[str, Any]) -> Any:
        req_id = self._next_id
        self._next_id += 1
        body = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
        payload = json.dumps(body, separators=(",", ":")).encode("utf-8")

        conn = HTTPConnection(self._host, self._port, timeout=self._timeout)
        try:
            try:
                conn.request(
                    "POST",
                    self._rpc_path,
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
                raise HostTransportConnectionError(
                    f"could not reach {self.endpoint}: {exc}"
                ) from exc
            except HTTPException as exc:
                raise HostTransportProtocolError(f"HTTP protocol error: {exc}") from exc
        finally:
            conn.close()

        if status == 204:
            return None
        if status != 200:
            raise HostTransportProtocolError(
                f"unexpected HTTP {status} from {self.endpoint}: {raw[:200]!r}"
            )
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HostTransportProtocolError(
                f"non-JSON response from {self.endpoint}: {exc}"
            ) from exc
        if not isinstance(data, dict) or data.get("jsonrpc") != "2.0":
            raise HostTransportProtocolError(f"not a JSON-RPC 2.0 response: {data!r}")
        if "error" in data:
            err = data["error"] or {}
            if not isinstance(err, dict):
                raise HostTransportProtocolError(f"malformed error object: {err!r}")
            raise HostTransportCallError(
                code=int(err.get("code", -32603)),
                message=str(err.get("message", "")),
                data=err.get("data"),
            )
        return data.get("result")


__all__ = [
    "HostTransportCallError",
    "HostTransportConnectionError",
    "HostTransportError",
    "HostTransportProtocolError",
    "HttpTransport",
]
