"""OpenClaw adapter implementing :class:`HostAdapter` (M5 #28).

Translates OpenClaw lifecycle events into :class:`JoinpointEvent`
envelopes the runtime can consume. The other half of the
:class:`HostAdapter` protocol — turning a :class:`ConcernInjection`
back into OpenClaw context — lands in #29 alongside the injector and
span extractor (this PR is intentionally tight).

Mapping flow (per event):

1. Coerce the input ``dict`` (or :class:`OpenClawEvent`) through
   ``OpenClawEvent.model_validate`` so we get a typed, ``extra=forbid``
   shape rather than a free-form mapping.
2. Look up the joinpoint name via :func:`lookup_joinpoint` — return
   ``None`` for events the plugin doesn't know about (e.g. a host
   extension that ships its own bespoke event names; the runtime
   simply ignores them rather than crashing on the wire).
3. Resolve the joinpoint level from :data:`JOINPOINT_CATALOG`. The
   v0.1 §12 catalog already lists every target our event-map points
   at; defensively fall back to :class:`JoinpointLevel.LIFECYCLE` if
   a future PR ever adds an event whose target isn't yet registered.
4. Fill ``id`` (uuid4) and ``ts`` (current UTC) when the inbound
   event omitted them.
5. Forward ``payload`` verbatim onto :attr:`JoinpointEvent.payload` so
   pointcut strategies see the OpenClaw payload as-is.

The host name is fixed to ``"openclaw"`` so downstream
``scope.crosscutting`` filters and DCN attributions can tell which
adapter produced an event when the daemon serves multiple hosts at
once (M7).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from COAT_runtime_core.joinpoint import JOINPOINT_CATALOG, JoinpointLevel
from COAT_runtime_core.ports import HostAdapter
from COAT_runtime_protocol import ConcernInjection, JoinpointEvent

from .events import OpenClawEvent
from .joinpoint_map import lookup_joinpoint

# Sentinel host name — also surfaces in :attr:`JoinpointEvent.host`.
_HOST_NAME = "openclaw"

# Default level for joinpoints whose name isn't in the v0.1 §12 catalog.
# Every entry our :mod:`joinpoint_map` produces _is_ in the catalog
# today, so this only fires if a future PR adds an event without
# registering its target.
_FALLBACK_LEVEL = JoinpointLevel.LIFECYCLE


class OpenClawAdapter(HostAdapter):
    """Map OpenClaw events → :class:`JoinpointEvent` + (later) apply injections."""

    @property
    def host_name(self) -> str:
        return _HOST_NAME

    # ------------------------------------------------------------------
    # event → joinpoint
    # ------------------------------------------------------------------

    def map_host_event(self, event: dict | OpenClawEvent) -> JoinpointEvent | None:
        """Translate a single OpenClaw event into a :class:`JoinpointEvent`.

        Returns ``None`` for events whose ``event_name`` isn't in the
        :data:`OPENCLAW_EVENT_MAP` table — the contract on
        :class:`HostAdapter`. Raises :class:`pydantic.ValidationError`
        when the input is structurally wrong (missing ``event_name``,
        unknown keys, bad types) so misconfigured hosts fail loudly.
        """
        oc = event if isinstance(event, OpenClawEvent) else OpenClawEvent.model_validate(event)

        joinpoint_name = lookup_joinpoint(oc.event_name)
        if joinpoint_name is None:
            return None

        entry = JOINPOINT_CATALOG.get(joinpoint_name)
        level = entry.level if entry is not None else _FALLBACK_LEVEL

        return JoinpointEvent(
            id=oc.id or str(uuid.uuid4()),
            level=int(level),
            name=joinpoint_name,
            host=_HOST_NAME,
            agent_session_id=oc.agent_session_id,
            turn_id=oc.turn_id,
            ts=oc.ts or datetime.now(tz=UTC),
            payload=oc.payload,
        )

    def map_host_events(
        self,
        events: Iterable[dict | OpenClawEvent],
    ) -> Iterable[JoinpointEvent]:
        """Streaming variant — yields successful mappings, drops :py:obj:`None`."""
        for event in events:
            jp = self.map_host_event(event)
            if jp is not None:
                yield jp

    # ------------------------------------------------------------------
    # injection → host context (M5 #29)
    # ------------------------------------------------------------------

    def apply_injection(
        self,
        injection: ConcernInjection,
        host_context: dict,
    ) -> dict[str, Any]:
        raise NotImplementedError(
            "OpenClawAdapter.apply_injection lands in M5 #29 (feat/m5-openclaw-injector)."
        )


__all__ = ["OpenClawAdapter"]
