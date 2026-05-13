"""Top-level :class:`Client` — chooses a transport based on the connect URI.

Connect string formats:

* ``inproc://`` — direct in-process call. Requires ``runtime=`` kwarg
  pointing at an :class:`opencoat_runtime_core.OpenCOATRuntime`-shaped
  object. No serialization; the host and runtime share memory.
* ``http://host:port`` / ``https://host:port`` — JSON-RPC 2.0 over HTTP.
  Path defaults to ``/rpc``; pass a path component in the URL to
  override (e.g. ``http://host:port/v1/opencoat``).
* ``unix:///run/opencoat.sock`` — Unix domain socket. **Not implemented**
  in 0.1.0; raises :class:`NotImplementedError`.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from opencoat_runtime_protocol import ConcernInjection, JoinpointEvent

from .transport.http import HttpTransport
from .transport.inproc import InProcTransport
from .transport.socket import SocketTransport


class Client:
    """Entrypoint for host code.

    Most callers use :meth:`connect`; pass a pre-built transport for
    tests or for transports we don't auto-detect.
    """

    def __init__(self, transport: Any) -> None:
        self._transport = transport

    @property
    def transport(self) -> Any:
        return self._transport

    @classmethod
    def connect(
        cls,
        uri: str,
        *,
        runtime: Any = None,
        timeout_seconds: float = 5.0,
    ) -> Client:
        """Connect to an OpenCOAT runtime via the transport implied by ``uri``.

        Args:
            uri: ``inproc://``, ``http(s)://…``, or ``unix://…``.
            runtime: only used for ``inproc://`` — the in-process runtime
                instance (typically ``OpenCOATRuntime``).
            timeout_seconds: HTTP only — per-request timeout.

        Raises:
            ValueError: when the URI scheme is unknown or when
                ``inproc://`` is requested without ``runtime=``.
            NotImplementedError: when a transport is recognised but not
                yet wired (currently: ``unix://``).
        """
        if not isinstance(uri, str) or not uri:
            raise ValueError("Client.connect uri must be a non-empty string")

        parsed = urlparse(uri)
        scheme = parsed.scheme.lower()

        if scheme == "inproc":
            if runtime is None:
                raise ValueError(
                    "Client.connect('inproc://…') requires runtime= to "
                    "point at an in-process OpenCOATRuntime instance"
                )
            return cls(InProcTransport(runtime))

        if scheme in ("http", "https"):
            return cls(HttpTransport(base_url=uri, timeout_seconds=timeout_seconds))

        if scheme == "unix":
            # Reserve the API shape; wiring lands with PR-X2 if/when we
            # actually need socket transport. HTTP covers daemon usage.
            path = parsed.path or uri[len("unix://") :]
            return cls(SocketTransport(path=path))

        raise ValueError(
            f"unsupported transport scheme {scheme!r} in {uri!r}; "
            "expected inproc://, http(s)://, or unix://"
        )

    def emit(
        self,
        joinpoint: JoinpointEvent,
        *,
        context: dict[str, Any] | None = None,
        return_none_when_empty: bool = False,
    ) -> ConcernInjection | None:
        """Submit ``joinpoint`` and return the runtime's injection, if any."""
        return self._transport.emit(
            joinpoint,
            context=context,
            return_none_when_empty=return_none_when_empty,
        )


__all__ = ["Client"]
