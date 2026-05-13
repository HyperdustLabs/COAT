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
        while turn := openclaw_host.next_turn():
            # 1. events get pushed into the runtime via the subscriptions
            #    install_hooks set up (concerns activate inside the daemon)
            turn.run_until_prompt()

            # 2. fold every active concern's advice back into the host's
            #    mutable prompt context BEFORE calling the LLM.
            turn.prompt_ctx = installed.apply_to(turn.prompt_ctx)

            # 3. before dispatching tool calls, decode any TOOL_GUARD
            #    advice the runtime emitted on ``before_tool_call``.
            for call in turn.pending_tool_calls():
                outcome = installed.guard_tool_call(call)
                if outcome is not None and outcome.blocked:
                    turn.refuse(call, reason=outcome.block_reason)
                elif outcome is not None:
                    turn.dispatch(call["name"], outcome.arguments, notes=outcome.notes)
                else:
                    turn.dispatch(call["name"], call["arguments"])
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
   :meth:`OpenCOATRuntime.on_joinpoint` (or any
   :class:`RuntimeLike`) and **captures the returned
   :class:`ConcernInjection`** into :attr:`InstalledHooks.pending` so
   the host can fold it back into its mutable state at prompt /
   tool-dispatch time via :meth:`InstalledHooks.apply_to` and
   :meth:`InstalledHooks.guard_tool_call`. Empty injections are
   skipped so the buffer only holds rows the host actually needs to
   apply.
4. For ``agent.memory_write`` specifically, also runs the raw payload
   through :meth:`OpenClawMemoryBridge.sync` so the DCN reflects the
   write (when wired with a store).

The returned :class:`InstalledHooks` retains every unsubscribe handle
the host returned so :meth:`InstalledHooks.uninstall` cleanly detaches
the whole adapter / bridge surface — important for tests and for
long-running daemons that re-bind hosts on reload.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from opencoat_runtime_protocol import ConcernInjection, JoinpointEvent

from .adapter import OpenClawAdapter
from .events import OpenClawEvent, OpenClawEventName
from .memory_bridge import OpenClawMemoryBridge
from .tool_guard import ToolGuardOutcome

# Joinpoint names whose injection should be fed through
# :meth:`OpenClawAdapter.guard_tool_call` rather than the generic
# :meth:`apply_injection` path. Today this is just ``before_tool_call``;
# kept as a module constant so future joinpoints (e.g. ``before_tool_result``)
# can opt in without touching :class:`InstalledHooks`.
_TOOL_GUARD_JOINPOINTS: frozenset[str] = frozenset({"before_tool_call"})

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


@dataclass(frozen=True)
class PendingInjection:
    """One ``(joinpoint, injection)`` pair captured by an
    :class:`InstalledHooks` callback, waiting to be folded into a host
    context (via :meth:`InstalledHooks.apply_to`) or decoded into a
    :class:`ToolGuardOutcome` (via :meth:`InstalledHooks.guard_tool_call`).

    Wrapped in a small dataclass rather than passed around as a bare
    tuple so debugging — ``print(installed.pending)`` — stays readable
    and so future fields (``recorded_at`` timestamps, vector snapshots,
    …) can land without changing the call sites.
    """

    joinpoint: JoinpointEvent
    injection: ConcernInjection


@dataclass
class InstalledHooks:
    """Handle returned by :func:`install_hooks`.

    Carries three things:

    * the **subscription handles** every well-known event name returned
      from :meth:`OpenClawHost.subscribe` — torn down by
      :meth:`uninstall`;
    * the **pending injection buffer** :attr:`pending` —
      ``(joinpoint, injection)`` pairs the event callbacks captured but
      the host hasn't applied yet; drained by :meth:`apply_to` /
      :meth:`guard_tool_call`;
    * the **adapter** / **runtime** / **bridge** references for hosts
      that want to drive the underlying surface directly (e.g. tests
      poking ``installed.adapter.guard_tool_call`` outside the
      pickup API).

    The pickup API closes the loop M5 #31 left half-wired: events get
    pushed into the runtime through ``subscribe`` callbacks, the
    returned :class:`ConcernInjection` is captured here, and the host
    materialises it back into its mutable state at prompt /
    tool-dispatch time.
    """

    host: OpenClawHost
    runtime: RuntimeLike
    adapter: OpenClawAdapter
    bridge: OpenClawMemoryBridge | None
    event_names: tuple[str, ...]
    _unsubscribes: list[Unsubscribe] = field(default_factory=list)
    _uninstalled: bool = False
    _pending: list[PendingInjection] = field(default_factory=list)

    @property
    def is_installed(self) -> bool:
        """``True`` until :meth:`uninstall` has fully detached."""
        return not self._uninstalled

    @property
    def pending(self) -> tuple[PendingInjection, ...]:
        """Read-only snapshot of buffered injections, oldest first.

        A tuple (rather than a list) so callers can't accidentally
        mutate the live buffer — the only supported mutation paths are
        :meth:`apply_to`, :meth:`guard_tool_call`, and
        :meth:`clear_pending`.
        """
        return tuple(self._pending)

    def clear_pending(self) -> None:
        """Drop every buffered injection without applying anything.

        Useful when the host wants to start a new turn fresh — e.g.
        after a turn was cancelled / errored before reaching its
        prompt-build step.
        """
        self._pending.clear()

    def apply_to(
        self,
        context: dict[str, Any] | None = None,
        *,
        joinpoint: str | None = None,
        drain: bool = True,
    ) -> dict[str, Any]:
        """Fold every buffered injection into ``context`` and return the result.

        This is the **prompt-folding** pickup point. The OpenClaw
        adapter's ``apply_injection`` (M5 #29) is finally called here,
        with rows the runtime decided to weave on each subscribed
        joinpoint.

        Parameters
        ----------
        context:
            Host's mutable state — typically a prompt context with
            ``runtime_prompt.*`` / ``response.*`` slots the adapter
            writes into. ``None`` is treated as ``{}`` so callers can
            ``installed.apply_to()`` for a "show me what concerns
            would inject" snapshot.
        joinpoint:
            Apply only rows captured for this joinpoint name (e.g.
            ``"before_response"`` for prompt folding, ``"on_user_input"``
            for early advice). ``None`` (default) applies every
            buffered row.
        drain:
            ``True`` (default) consumes the applied rows so they
            don't double-apply on the next call. ``False`` peeks
            without consuming — handy for tests and snapshots.

        Returns
        -------
        A new context dict that the caller can freely mutate without
        leaking changes back to ``context``. Two code paths uphold
        this contract:

        * **At least one applicable row** — the returned dict comes
          from :meth:`OpenClawAdapter.apply_injection`, which already
          deep-copies its input. We pass the caller's dict through
          unchanged and rely on that.
        * **No applicable rows** (buffer empty, every entry filtered
          out by ``joinpoint=``, or only tool-guard rows present) —
          ``apply_injection`` is never called, so we run an explicit
          :func:`copy.deepcopy` here. Without it, ``dict(context)``
          would only clone the top level and the caller's nested
          slots (e.g. ``context["runtime_prompt"]``) would remain
          aliased through the return value (Codex P2 on PR #47).
        """
        kept: list[PendingInjection] = []
        applicable: list[PendingInjection] = []
        for entry in self._pending:
            if joinpoint is not None and entry.joinpoint.name != joinpoint:
                kept.append(entry)
                continue
            # Skip tool-guard joinpoints in the generic apply_to path —
            # those have a structured outcome surface
            # (``guard_tool_call``) and folding them blindly into a
            # prompt context would corrupt the ``tool_call.*`` slot.
            if entry.joinpoint.name in _TOOL_GUARD_JOINPOINTS:
                kept.append(entry)
                continue
            applicable.append(entry)

        if applicable:
            # ``adapter.apply_injection`` deep-copies internally — no
            # need to clone here, which would just produce a doubly-
            # copied intermediate dict.
            out: dict[str, Any] = dict(context) if context else {}
            for entry in applicable:
                out = self.adapter.apply_injection(entry.injection, out)
        else:
            out = copy.deepcopy(context) if context else {}

        if drain:
            self._pending[:] = kept
        return out

    def guard_tool_call(
        self,
        tool_call: dict[str, Any],
        *,
        drain: bool = True,
    ) -> ToolGuardOutcome | None:
        """Decode the most recent ``before_tool_call`` advice for ``tool_call``.

        Walks the buffer from newest to oldest looking for an injection
        captured on a tool-guard joinpoint (today: ``before_tool_call``),
        runs it through :meth:`OpenClawAdapter.guard_tool_call`, and
        returns the structured :class:`ToolGuardOutcome`.

        Returns ``None`` when no tool-guard injection is buffered — the
        host should default-allow the call in that case.

        ``drain=True`` (default) removes the consumed buffer entry so
        the same advice doesn't fire on the next call; ``drain=False``
        is intended for inspection / tests.
        """
        for i in range(len(self._pending) - 1, -1, -1):
            entry = self._pending[i]
            if entry.joinpoint.name in _TOOL_GUARD_JOINPOINTS:
                outcome = self.adapter.guard_tool_call(tool_call, entry.injection)
                if drain:
                    del self._pending[i]
                return outcome
        return None

    def uninstall(self) -> None:
        """Call every unsubscribe handle and mark the bundle as detached.

        Safe to call multiple times — subsequent calls are no-ops so a
        host can wire ``uninstall`` to a ``finally`` block without
        worrying about idempotency.

        Does **not** clear :attr:`pending` — the host may still want
        to apply / inspect buffered injections during teardown. Call
        :meth:`clear_pending` explicitly when that's desired.
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
            installed=installed,
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
    installed: InstalledHooks,
) -> HostCallback:
    """Build the single per-event callback we hand to ``host.subscribe``.

    Kept as a free function so the captured closure cell is tiny and
    each event-name's binding stays independent (Python's late binding
    on for-loops bit us before — keep this defensive).

    The callback closes over ``installed`` so it can park the runtime's
    :class:`ConcernInjection` on
    :attr:`InstalledHooks._pending`. This is the half of M5 #31 that
    was missing — without it, the runtime's advice was computed and
    thrown away inside the callback (events flowed in, injections
    never flowed back out to the host).
    """
    is_memory_event = name == _MEMORY_EVENT

    def _callback(payload: dict[str, Any]) -> None:
        envelope = _to_envelope(payload, name)

        # 1. event → joinpoint → runtime → captured injection
        joinpoint = adapter.map_host_event(envelope)
        if joinpoint is not None:
            injection = runtime.on_joinpoint(joinpoint)
            # Empty injections (no concerns matched) don't earn a
            # buffer slot — they'd just be no-ops at apply_to time and
            # would muddy `installed.pending` snapshots during debug.
            if injection is not None and injection.injections:
                installed._pending.append(
                    PendingInjection(joinpoint=joinpoint, injection=injection)
                )

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
    "PendingInjection",
    "RuntimeLike",
    "install_hooks",
]
