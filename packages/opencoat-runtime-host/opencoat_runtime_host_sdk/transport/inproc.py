"""In-process transport — direct function call on a local runtime.

Use this when the host **and** the runtime live in the same Python
process (the topology ADR 0005 calls "embedded"). No serialization, no
sockets — :meth:`emit` just hands the joinpoint to
``runtime.on_joinpoint`` and returns whatever the runtime produced.

For the host-in-process-A, daemon-in-process-B case use
:class:`~opencoat_runtime_host_sdk.transport.http.HttpTransport` instead.
"""

from __future__ import annotations

from typing import Any, Protocol

from opencoat_runtime_protocol import ConcernInjection, JoinpointEvent


class _RuntimeLike(Protocol):
    """Structural type matching :class:`opencoat_runtime_core.OpenCOATRuntime`.

    Kept local so this module stays runtime-free at import time — the
    actual ``OpenCOATRuntime`` lives in ``opencoat-runtime`` and we
    only depend on the one method we need.
    """

    def on_joinpoint(
        self,
        jp: JoinpointEvent,
        *,
        context: dict[str, Any] | None = ...,
        return_none_when_empty: bool = ...,
    ) -> ConcernInjection | None: ...


class InProcTransport:
    """Submit joinpoints to a runtime running in this Python process."""

    def __init__(self, runtime: _RuntimeLike) -> None:
        self._runtime = runtime

    def emit(
        self,
        joinpoint: JoinpointEvent,
        *,
        context: dict[str, Any] | None = None,
        return_none_when_empty: bool = False,
    ) -> ConcernInjection | None:
        return self._runtime.on_joinpoint(
            joinpoint,
            context=context,
            return_none_when_empty=return_none_when_empty,
        )


__all__ = ["InProcTransport"]
