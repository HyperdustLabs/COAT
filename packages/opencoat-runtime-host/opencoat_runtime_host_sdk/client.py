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

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from opencoat_runtime_protocol import Concern, ConcernInjection, JoinpointEvent

from .transport.http import HttpTransport
from .transport.inproc import InProcTransport


@dataclass(frozen=True, slots=True)
class ExtractionRejection:
    """One span the extractor rejected, with a short reason.

    Mirrors :class:`opencoat_runtime_core.concern.Rejection` on purpose
    so host code only ever imports from ``opencoat-runtime-host`` —
    the host SDK stays consumable without ``opencoat-runtime-core``
    on the import path for pure-protocol callers.
    """

    span: str
    reason: str


@dataclass(frozen=True, slots=True)
class ExtractionOutcome:
    """Typed result of :meth:`Client.extract_concerns`.

    Attributes
    ----------
    candidates:
        Validated :class:`Concern` envelopes the extractor produced,
        in source order, already de-duplicated within this call.
    rejected:
        Per-span :class:`ExtractionRejection` entries — LLM error,
        envelope validation error, duplicate, etc. Hosts surface
        these as warnings; they do not abort the call.
    upserted:
        ``True`` when the daemon (or in-proc runtime) wrote every
        candidate into its concern store before responding. ``False``
        when the caller passed ``dry_run=True`` for a preview-only
        run, in which case the candidates exist in memory only and
        won't be visible to a subsequent ``joinpoint.submit``.
    """

    candidates: tuple[Concern, ...] = ()
    rejected: tuple[ExtractionRejection, ...] = field(default_factory=tuple)
    upserted: bool = True

    def __bool__(self) -> bool:  # pragma: no cover — trivial
        return bool(self.candidates)

    def __len__(self) -> int:  # pragma: no cover — trivial
        return len(self.candidates)


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
            NotImplementedError: when a scheme is reserved but not yet
                wired — currently ``unix://``. Raised at connect time
                (not at first ``.emit()``) so the failure mode is
                obvious from the call site.
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
            # The wire surface is reserved (see SocketTransport) but the
            # daemon doesn't expose a UDS listener yet and there's no
            # client-side parser for it. Fail loudly at connect time so
            # callers don't get a confusing ``TypeError`` from a stub
            # ``emit`` later. HTTP covers every daemon topology today.
            raise NotImplementedError(
                "unix:// transport is reserved but not wired in 0.1.0; "
                "use http://host:port against the daemon's HTTP listener."
            )

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

    def extract_concerns(
        self,
        text: str,
        *,
        origin: str,
        ref: str | None = None,
        dry_run: bool = False,
    ) -> ExtractionOutcome:
        """Turn natural-language ``text`` into Concerns via the runtime's LLM.

        Bridges the host loop into
        :class:`opencoat_runtime_core.concern.ConcernExtractor` (the
        OpenCOAT runtime's M2 §20.1 extractor) over the wire surface
        introduced in M5 PR-48 — ``concern.extract``. Works identically
        for ``inproc://`` and ``http(s)://`` transports.

        Parameters
        ----------
        text:
            The natural-language input to mine (a user message,
            a governance paragraph, a tool log, …). Must be non-empty
            after stripping.
        origin:
            One of ``manual_import`` / ``user_input`` / ``tool_result``
            / ``draft_output`` / ``feedback``. Selects the per-origin
            LLM instruction and the default trust score the extractor
            stamps onto the produced :class:`Concern.source`. Anything
            else raises :class:`ValueError` (HTTP) or surfaces as
            ``-32602 invalid params`` (RPC).
        ref:
            Optional provenance handle (prompt id, document ref, tool
            name, …). Stamped verbatim onto ``Concern.source.ref``.
        dry_run:
            When ``True``, the daemon (or in-proc runtime) skips the
            ``concern_store.upsert`` step so candidates are *not*
            visible to a subsequent ``joinpoint.submit``. Useful for
            CLI ``--dry-run`` previews; defaults to ``False`` so
            "extract → next turn picks it up" works in one call.

        Returns
        -------
        :class:`ExtractionOutcome` carrying the validated candidates,
        any per-span rejections, and whether the upsert side-effect
        actually fired.
        """
        params: dict[str, Any] = {"text": text, "origin": origin}
        if ref is not None:
            params["ref"] = ref
        if dry_run:
            params["dry_run"] = True

        raw = self._transport.call("concern.extract", params)
        if not isinstance(raw, dict):
            raise RuntimeError(f"extract_concerns: malformed result from transport: {raw!r}")
        candidates = tuple(Concern.model_validate(c) for c in raw.get("candidates", []))
        rejected = tuple(
            ExtractionRejection(
                span=str(r.get("span", "")),
                reason=str(r.get("reason", "")),
            )
            for r in raw.get("rejected", [])
        )
        upserted = bool(raw.get("upserted", not dry_run))
        return ExtractionOutcome(candidates=candidates, rejected=rejected, upserted=upserted)


__all__ = ["Client", "ExtractionOutcome", "ExtractionRejection"]
