"""Wire an :class:`OpenClawAdapter` (+ optional memory bridge) into an
OpenClaw-shaped host's lifecycle (M5 #31).

OpenClaw doesn't ship a typed event SDK we can import — this module
defines the **subscribe-shaped** Protocol the adapter expects, plus the
function that registers callbacks for every well-known OpenClaw event
name. The intent is that a real OpenClaw integration ends up looking
like:

.. code-block:: python

    from opencoat_runtime_host_openclaw import (
        OpenClawAdapter,
        OpenClawMemoryBridge,
        install_hooks,
    )

    installed = install_hooks(
        host=openclaw_host,
        runtime=runtime,
        adapter=OpenClawAdapter(),
        bridge=OpenClawMemoryBridge(dcn_store=runtime.dcn_store),
    )
    try:
        openclaw_host.run()
    finally:
        installed.uninstall()

For each :class:`~.events.OpenClawEventName` the bridge subscribes a
callback that:

1. Validates the raw payload as :class:`~.events.OpenClawEvent`.
2. Maps it to a :class:`JoinpointEvent` via
   :meth:`OpenClawAdapter.map_host_event` — events the adapter doesn't
   know about (returns ``None``) are dropped silently so the host can
   evolve its event surface without breaking the integration.
3. Forwards the mapped joinpoint to
   :meth:`OpenCOATRuntime.on_joinpoint`.
4. For ``agent.memory_write`` specifically, also runs the raw payload
   through :meth:`OpenClawMemoryBridge.sync` so the DCN reflects the
   write (when wired with a store).

The returned :class:`InstalledHooks` retains every unsubscribe handle
the host returned so :meth:`InstalledHooks.uninstall` cleanly detaches
the whole adapter / bridge surface — important for tests and for
long-running daemons that re-bind hosts on reload.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from opencoat_runtime_protocol import ConcernInjection, JoinpointEvent

from .adapter import OpenClawAdapter
from .events import OpenClawEvent, OpenClawEventName
from .memory_bridge import OpenClawMemoryBridge

# Field names that live on :class:`OpenClawEvent` itself rather than
# the per-event body. Used to coerce flat host payloads into the
# envelope shape the adapter expects without losing turn correlation.
_ENVELOPE_FIELDS = frozenset(OpenClawEvent.model_fields.keys())


@runtime_checkable
class RuntimeLike(Protocol):
    """Structural shape :func:`install_hooks` needs from a runtime.

    The concrete :class:`opencoat_runtime_core.OpenCOATRuntime`
    satisfies this naturally, but so does any object that forwards
    joinpoints elsewhere — e.g. a thin proxy over
    :class:`opencoat_runtime_host_sdk.Client` that routes every
    submit through HTTP JSON-RPC to a running daemon. This is what
    the daemon-backed ``opencoat plugin install openclaw`` scaffold
    uses to share concern + DCN state with ``opencoat runtime up``.
    """

    def on_joinpoint(
        self,
        jp: JoinpointEvent,
        *,
        context: dict[str, Any] | None = ...,
        return_none_when_empty: bool = ...,
    ) -> ConcernInjection | None: ...


# Type aliases — keep callback signatures readable.
HostCallback = Callable[[dict[str, Any]], None]
Unsubscribe = Callable[[], None]

# Event we forward through the bridge in addition to the runtime path.
_MEMORY_EVENT = OpenClawEventName.AGENT_MEMORY_WRITE.value


@runtime_checkable
class OpenClawHost(Protocol):
    """Duck-typed subscribe surface :func:`install_hooks` drives.

    A "real" OpenClaw integration wraps its own event bus to satisfy
    this Protocol. Tests use a tiny in-memory fake (see
    ``tests/test_openclaw_install_hooks.py``).
    """

    def subscribe(self, event_name: str, callback: HostCallback) -> Unsubscribe:
        """Register ``callback`` for ``event_name`` and return an
        unsubscribe function the bridge calls on teardown.
        """
        ...


@dataclass
class InstalledHooks:
    """Handle returned by :func:`install_hooks` — call ``.uninstall()``
    to detach every registered callback.
    """

    host: OpenClawHost
    runtime: RuntimeLike
    adapter: OpenClawAdapter
    bridge: OpenClawMemoryBridge | None
    event_names: tuple[str, ...]
    _unsubscribes: list[Unsubscribe] = field(default_factory=list)
    _uninstalled: bool = False

    @property
    def is_installed(self) -> bool:
        """``True`` until :meth:`uninstall` has fully detached."""
        return not self._uninstalled

    def uninstall(self) -> None:
        """Call every unsubscribe handle and mark the bundle as detached.

        Safe to call multiple times — subsequent calls are no-ops so a
        host can wire ``uninstall`` to a ``finally`` block without
        worrying about idempotency.
        """
        if self._uninstalled:
            return
        for fn in self._unsubscribes:
            fn()
        self._unsubscribes.clear()
        self._uninstalled = True


def install_hooks(
    host: OpenClawHost,
    *,
    runtime: RuntimeLike,
    adapter: OpenClawAdapter | None = None,
    bridge: OpenClawMemoryBridge | None = None,
    event_names: tuple[str, ...] | None = None,
) -> InstalledHooks:
    """Subscribe adapter callbacks for every well-known OpenClaw event.

    Parameters
    ----------
    host:
        Anything satisfying :class:`OpenClawHost` — i.e. exposes a
        ``subscribe(event_name, callback) -> unsubscribe`` method.
    runtime:
        Anything satisfying :class:`RuntimeLike` — typically a real
        :class:`opencoat_runtime_core.OpenCOATRuntime`, but a thin
        proxy over a daemon :class:`Client` also works (and is what
        the daemon-backed ``plugin install`` scaffold uses).
    adapter:
        :class:`OpenClawAdapter` used for event → joinpoint mapping. A
        fresh adapter is constructed when omitted, but in practice the
        same instance should be shared with whoever applies injections
        / guards tool calls so config (e.g.
        ``inject_into_runtime_prompt``) stays consistent.
    bridge:
        Optional :class:`OpenClawMemoryBridge` that mirrors
        ``agent.memory_write`` events onto the DCN. ``None`` skips the
        bridge call entirely; the memory event still maps through to
        ``runtime.on_joinpoint`` as ``before_memory_write``.
    event_names:
        Override which event names get subscribed. Defaults to every
        value in :class:`OpenClawEventName` — useful for tests that want
        to inspect a narrower surface.
    """
    adapter = adapter or OpenClawAdapter()
    names = event_names if event_names is not None else _default_event_names()

    installed = InstalledHooks(
        host=host,
        runtime=runtime,
        adapter=adapter,
        bridge=bridge,
        event_names=names,
    )

    for name in names:
        callback = _make_callback(
            name=name,
            adapter=adapter,
            runtime=runtime,
            bridge=bridge,
        )
        unsubscribe = host.subscribe(name, callback)
        installed._unsubscribes.append(unsubscribe)

    return installed


# ---------------------------------------------------------------------------
# internals
# ---------------------------------------------------------------------------


def _default_event_names() -> tuple[str, ...]:
    """Every well-known OpenClaw event name, in enum-declaration order."""
    return tuple(name.value for name in OpenClawEventName)


def _make_callback(
    *,
    name: str,
    adapter: OpenClawAdapter,
    runtime: RuntimeLike,
    bridge: OpenClawMemoryBridge | None,
) -> HostCallback:
    """Build the single per-event callback we hand to ``host.subscribe``.

    Kept as a free function so the captured closure cell is tiny and
    each event-name's binding stays independent (Python's late binding
    on for-loops bit us before — keep this defensive).
    """
    is_memory_event = name == _MEMORY_EVENT

    def _callback(payload: dict[str, Any]) -> None:
        envelope = _to_envelope(payload, name)

        # 1. event → joinpoint → runtime
        joinpoint = adapter.map_host_event(envelope)
        if joinpoint is not None:
            runtime.on_joinpoint(joinpoint)

        # 2. memory_write side-channel — mirror into the DCN when wired
        if is_memory_event and bridge is not None:
            bridge.sync(_extract_memory_payload(envelope, payload))

    return _callback


def _to_envelope(raw: dict[str, Any], name: str) -> dict[str, Any]:
    """Coerce a host-emitted payload into the :class:`OpenClawEvent` shape.

    OpenClaw subscribers typically receive a flat dict carrying both
    envelope-ish fields (``turn_id``, ``agent_session_id``) and the
    event body (``text``, ``key``, …) at the top level. The adapter
    needs them split. This helper:

    * Detects an already-envelope-shaped dict (``payload`` is a nested
      dict, or ``event_name`` is present) and only fills in
      ``event_name`` when missing.
    * Otherwise splits known envelope fields out and tucks the rest
      under ``payload``.

    Never mutates ``raw``.
    """
    if "event_name" in raw or isinstance(raw.get("payload"), dict):
        if "event_name" in raw:
            return raw
        return {**raw, "event_name": name}

    envelope: dict[str, Any] = {"event_name": name}
    body: dict[str, Any] = {}
    for key, value in raw.items():
        if key in _ENVELOPE_FIELDS:
            envelope[key] = value
        else:
            body[key] = value
    if body:
        envelope["payload"] = body
    return envelope


def _extract_memory_payload(
    envelope: dict[str, Any],
    raw: dict[str, Any],
) -> dict[str, Any]:
    """Pull the memory-write body out of an event envelope.

    Prefers the structured ``envelope["payload"]`` (typed in the
    :class:`OpenClawEvent` model); falls back to ``raw`` when the host
    bypassed the envelope and emitted bare memory fields.
    """
    inner = envelope.get("payload")
    if isinstance(inner, dict):
        return inner
    return raw


__all__ = [
    "InstalledHooks",
    "OpenClawHost",
    "RuntimeLike",
    "install_hooks",
]
