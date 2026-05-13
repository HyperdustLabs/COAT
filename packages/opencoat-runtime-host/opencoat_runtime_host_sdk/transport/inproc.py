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
    only depend on the methods we need:

    * :meth:`on_joinpoint` — the headline turn-loop entry point that
      :meth:`InProcTransport.emit` drives.
    * :attr:`llm` and :attr:`concern_store` — exposed by
      ``OpenCOATRuntime`` since M5 PR-48 so the in-proc transport can
      drive ``concern.extract`` without going through the daemon's
      :class:`JsonRpcHandler` (which would import the daemon module
      and widen this transport's dependency surface).
    """

    def on_joinpoint(
        self,
        jp: JoinpointEvent,
        *,
        context: dict[str, Any] | None = ...,
        return_none_when_empty: bool = ...,
    ) -> ConcernInjection | None: ...

    @property
    def llm(self) -> Any: ...

    @property
    def concern_store(self) -> Any: ...


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

    def call(self, method: str, params: dict[str, Any]) -> Any:
        """Generic JSON-RPC-shaped dispatch for in-proc callers.

        The HTTP transport's :meth:`~HttpTransport.call` reaches the
        daemon's wire dispatcher; in-proc we serve the same RPC
        surface directly so :class:`Client.extract_concerns` works
        identically against ``inproc://`` and ``http://``. Today we
        cover the methods the host SDK actually drives in-proc
        (``concern.extract``, plus the existing ``joinpoint.submit``
        path for symmetry); other methods raise
        :class:`NotImplementedError` rather than pretending to dispatch
        — hosts wanting full RPC surface in-proc should mount
        :class:`opencoat_runtime_daemon.ipc.jsonrpc_dispatch.JsonRpcHandler`
        directly.
        """
        if method == "joinpoint.submit":
            return self._call_joinpoint_submit(params)
        if method == "concern.extract":
            return self._call_concern_extract(params)
        raise NotImplementedError(
            f"InProcTransport.call: {method!r} is not exposed over the "
            "in-proc transport; mount opencoat_runtime_daemon."
            "ipc.jsonrpc_dispatch.JsonRpcHandler against the runtime "
            "for the full RPC surface."
        )

    def _call_joinpoint_submit(self, params: dict[str, Any]) -> Any:
        raw = params.get("joinpoint")
        if not isinstance(raw, dict):
            raise ValueError("joinpoint must be an object")
        jp = JoinpointEvent.model_validate(raw)
        ctx = params.get("context")
        context = ctx if isinstance(ctx, dict) else None
        ret_none = bool(params.get("return_none_when_empty", False))
        inj = self._runtime.on_joinpoint(jp, context=context, return_none_when_empty=ret_none)
        return None if inj is None else inj.model_dump(mode="json")

    def _call_concern_extract(self, params: dict[str, Any]) -> dict[str, Any]:
        # Lazy import to keep the host SDK importable on machines that
        # have ``opencoat-runtime-host`` but not ``opencoat-runtime``
        # (e.g. a pure-protocol consumer). The actual call site only
        # reaches this on hosts that *also* installed the runtime,
        # since the in-proc transport requires an ``OpenCOATRuntime``
        # instance.
        from opencoat_runtime_core.concern import ConcernExtractor

        text = params.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("text must be a non-empty string")
        origin = params.get("origin")
        if not isinstance(origin, str) or not origin:
            raise ValueError("origin must be a non-empty string")
        if origin not in ConcernExtractor.supported_origins():
            allowed = ", ".join(ConcernExtractor.supported_origins())
            raise ValueError(f"unsupported origin {origin!r}; expected one of: {allowed}")
        ref = params.get("ref")
        if ref is not None and not isinstance(ref, str):
            raise ValueError("ref must be a string when provided")
        dry_run = params.get("dry_run", False)
        if not isinstance(dry_run, bool):
            raise ValueError("dry_run must be a boolean when provided")

        extractor = ConcernExtractor(llm=self._runtime.llm)
        result = extractor.extract(text, origin=origin, ref=ref)
        if not dry_run:
            for c in result.candidates:
                self._runtime.concern_store.upsert(c)
        return {
            "candidates": [c.model_dump(mode="json") for c in result.candidates],
            "rejected": [{"span": r.span, "reason": r.reason} for r in result.rejected],
            "upserted": not dry_run,
        }


__all__ = ["InProcTransport"]
