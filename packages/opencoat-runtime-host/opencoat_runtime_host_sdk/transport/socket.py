"""Unix domain socket transport — reserved for a future milestone.

Direct daemon → host UDS communication is on the roadmap (ADR 0005, the
"sidecar" topology) but not wired in 0.1.0. The class is kept so
downstream code can type-annotate against ``SocketTransport`` and so
:class:`~opencoat_runtime_host_sdk.client.Client.connect` has a
recognised scheme to reject up front — instead of letting callers
discover the gap at first ``emit``.

For daemon usage today, use
:class:`~opencoat_runtime_host_sdk.transport.http.HttpTransport`.
"""

from __future__ import annotations

from typing import Any

from opencoat_runtime_protocol import ConcernInjection, JoinpointEvent


class SocketTransport:
    """Reserved transport — every call raises :class:`NotImplementedError`."""

    def __init__(self, *, path: str) -> None:
        self._path = path

    @property
    def path(self) -> str:
        return self._path

    def emit(
        self,
        joinpoint: JoinpointEvent,
        *,
        context: dict[str, Any] | None = None,
        return_none_when_empty: bool = False,
    ) -> ConcernInjection | None:
        # Signature mirrors :class:`HttpTransport` / :class:`InProcTransport`
        # on purpose: callers who construct a ``SocketTransport`` directly
        # (instead of going through ``Client.connect``) should hit a clean
        # ``NotImplementedError`` rather than a ``TypeError`` from a
        # mismatched signature.
        raise NotImplementedError(
            "SocketTransport is reserved for a future milestone; "
            "use HttpTransport (or Client.connect('http://…')) today."
        )


__all__ = ["SocketTransport"]
