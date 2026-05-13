"""Tests for :func:`install_hooks` + :class:`InstalledHooks` (M5 #31)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pytest
from opencoat_runtime_core import OpenCOATRuntime, RuntimeConfig
from opencoat_runtime_core.llm import StubLLMClient
from opencoat_runtime_host_openclaw import (
    InstalledHooks,
    OpenClawAdapter,
    OpenClawEventName,
    OpenClawHost,
    OpenClawMemoryBridge,
    install_hooks,
)
from opencoat_runtime_protocol import Concern, Pointcut
from opencoat_runtime_storage.memory import MemoryConcernStore, MemoryDCNStore
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# fakes
# ---------------------------------------------------------------------------


@dataclass
class FakeHost:
    """Records subscribe / unsubscribe calls + replays events."""

    subscriptions: dict[str, list[Callable[[dict[str, Any]], None]]] = field(default_factory=dict)
    unsubscribe_count: int = 0

    def subscribe(
        self,
        event_name: str,
        callback: Callable[[dict[str, Any]], None],
    ) -> Callable[[], None]:
        self.subscriptions.setdefault(event_name, []).append(callback)

        def _unsubscribe() -> None:
            self.unsubscribe_count += 1
            self.subscriptions[event_name].remove(callback)

        return _unsubscribe

    def fire(self, event_name: str, payload: dict[str, Any]) -> None:
        for cb in list(self.subscriptions.get(event_name, [])):
            cb(payload)


def _build_runtime() -> OpenCOATRuntime:
    return OpenCOATRuntime(
        RuntimeConfig(),
        concern_store=MemoryConcernStore(),
        dcn_store=MemoryDCNStore(),
        llm=StubLLMClient(),
    )


def _seed_concern(runtime: OpenCOATRuntime, concern_id: str, *, name: str = "stub") -> None:
    """Add a minimal concern node so ``log_activation`` doesn't reject."""
    runtime.dcn_store.add_node(
        Concern(
            id=concern_id,
            name=name,
            pointcut=Pointcut(),
        )
    )


# ---------------------------------------------------------------------------
# OpenClawHost protocol shape
# ---------------------------------------------------------------------------


class TestOpenClawHostProtocol:
    def test_fake_host_is_recognised_as_openclaw_host(self) -> None:
        assert isinstance(FakeHost(), OpenClawHost)

    def test_plain_object_is_not_an_openclaw_host(self) -> None:
        assert not isinstance(object(), OpenClawHost)


# ---------------------------------------------------------------------------
# install_hooks — subscription bookkeeping
# ---------------------------------------------------------------------------


class TestInstallSubscriptions:
    def test_subscribes_every_known_event_name_by_default(self) -> None:
        host = FakeHost()
        installed = install_hooks(host, runtime=_build_runtime())
        assert set(host.subscriptions.keys()) == {name.value for name in OpenClawEventName}
        assert installed.is_installed is True

    def test_event_names_argument_overrides_default(self) -> None:
        host = FakeHost()
        install_hooks(
            host,
            runtime=_build_runtime(),
            event_names=("agent.user_message", "agent.before_tool"),
        )
        assert set(host.subscriptions.keys()) == {
            "agent.user_message",
            "agent.before_tool",
        }

    def test_installed_hooks_returns_adapter_runtime_bridge(self) -> None:
        host = FakeHost()
        runtime = _build_runtime()
        adapter = OpenClawAdapter()
        bridge = OpenClawMemoryBridge(dcn_store=runtime.dcn_store)
        installed = install_hooks(
            host,
            runtime=runtime,
            adapter=adapter,
            bridge=bridge,
        )
        assert isinstance(installed, InstalledHooks)
        assert installed.host is host
        assert installed.runtime is runtime
        assert installed.adapter is adapter
        assert installed.bridge is bridge

    def test_default_adapter_is_constructed_when_omitted(self) -> None:
        host = FakeHost()
        installed = install_hooks(host, runtime=_build_runtime())
        assert isinstance(installed.adapter, OpenClawAdapter)
        assert installed.bridge is None


# ---------------------------------------------------------------------------
# install_hooks — runtime dispatch
# ---------------------------------------------------------------------------


class TestRuntimeDispatch:
    def test_user_message_routes_through_runtime(self) -> None:
        host = FakeHost()
        runtime = _build_runtime()
        install_hooks(host, runtime=runtime)

        host.fire("agent.user_message", {"turn_id": "t-1", "payload": {"text": "hi"}})

        # Snapshot bumps pending_event_count? No — on_joinpoint is the
        # turn loop, not the event loop. We rely on the fact that an
        # active turn has a last-vector (possibly None when no concerns
        # matched, but the call should not raise).
        snapshot = runtime.snapshot()
        assert snapshot is not None  # contract sanity

    def test_unknown_event_name_is_swallowed_silently(self) -> None:
        """Subscribing to a custom event name routes through the adapter
        too — the adapter returns ``None`` for unknown joinpoints and
        the callback drops it without raising."""
        host = FakeHost()
        runtime = _build_runtime()
        install_hooks(
            host,
            runtime=runtime,
            event_names=("agent.custom_x",),
        )
        host.fire("agent.custom_x", {"turn_id": "t-1", "payload": {}})

    def test_callback_injects_event_name_when_payload_omits_it(self) -> None:
        """Real OpenClaw delivers the payload *without* echoing the
        event name. The wrapper must inject it so the adapter's typed
        validator doesn't reject the dict."""
        host = FakeHost()
        runtime = _build_runtime()
        install_hooks(host, runtime=runtime)
        # No event_name in payload — must not raise.
        host.fire("agent.user_message", {"turn_id": "t-1"})

    def test_invalid_envelope_field_propagates_validation_error(self) -> None:
        """Type-invalid envelope fields (``ts`` not a datetime, etc.)
        surface as ``ValidationError`` so misconfigured hosts fail
        loudly. Unknown fields are tolerated by being routed to
        ``payload`` — see ``_to_envelope`` for the coercion rules."""
        host = FakeHost()
        runtime = _build_runtime()
        install_hooks(host, runtime=runtime)
        with pytest.raises(ValidationError):
            host.fire(
                "agent.user_message",
                # ``ts`` must parse as a datetime — bool is not coercible.
                {"turn_id": "t-1", "ts": True},
            )

    def test_unknown_flat_fields_are_tucked_under_payload(self) -> None:
        """Real OpenClaw subscribers receive the event body directly
        (e.g. ``{"text": "hi"}`` for ``agent.user_message``). The
        callback splits envelope fields out and wraps the rest under
        ``payload`` so the adapter validation succeeds."""
        host = FakeHost()
        runtime = _build_runtime()
        install_hooks(host, runtime=runtime)
        host.fire(
            "agent.user_message",
            {"turn_id": "t-1", "text": "hello"},
        )

    def test_envelope_shaped_payload_is_accepted_as_is(self) -> None:
        """When the host already emits ``{turn_id, payload: {...}}``
        the callback only fills in ``event_name`` and leaves the
        envelope intact."""
        host = FakeHost()
        runtime = _build_runtime()
        install_hooks(host, runtime=runtime)
        host.fire(
            "agent.user_message",
            {"turn_id": "t-1", "payload": {"text": "hi"}},
        )


# ---------------------------------------------------------------------------
# install_hooks — memory bridge side-channel
# ---------------------------------------------------------------------------


class TestMemoryBridgeSidechannel:
    def test_memory_write_event_calls_bridge_sync(self) -> None:
        host = FakeHost()
        runtime = _build_runtime()
        _seed_concern(runtime, "c-curiosity")
        store = runtime.dcn_store
        bridge = OpenClawMemoryBridge(dcn_store=store)
        install_hooks(host, runtime=runtime, bridge=bridge)

        host.fire(
            "agent.memory_write",
            {
                "turn_id": "t-1",
                "payload": {
                    "key": "episodic.q42",
                    "value": "42",
                    "concern_id": "c-curiosity",
                },
            },
        )
        # log_activation lands on the in-memory dcn_store; pull it back
        # via activation_log on the store directly.
        log = list(store.activation_log(concern_id="c-curiosity"))
        assert len(log) == 1
        # Schema isn't standardised across stores yet — at minimum the
        # joinpoint id should reflect the memory key.
        first = log[0]
        assert any("episodic.q42" in str(v) for v in first.values())

    def test_memory_write_against_unknown_concern_does_not_crash(self) -> None:
        """No seeded concern → bridge swallows ``KeyError`` and the
        host's event loop keeps running."""
        host = FakeHost()
        runtime = _build_runtime()
        bridge = OpenClawMemoryBridge(dcn_store=runtime.dcn_store)
        install_hooks(host, runtime=runtime, bridge=bridge)
        host.fire(
            "agent.memory_write",
            {
                "turn_id": "t-1",
                "payload": {"key": "k", "concern_id": "c-archived"},
            },
        )
        # No activation persisted because the concern wasn't there.
        assert list(runtime.dcn_store.activation_log(concern_id="c-archived")) == []

    def test_memory_write_without_bridge_does_not_raise(self) -> None:
        host = FakeHost()
        runtime = _build_runtime()
        install_hooks(host, runtime=runtime)  # bridge=None
        host.fire(
            "agent.memory_write",
            {"turn_id": "t-1", "payload": {"key": "k"}},
        )

    def test_non_memory_events_do_not_touch_bridge(self) -> None:
        host = FakeHost()
        runtime = _build_runtime()
        # Sentinel bridge: if .sync gets called we'll know via the side
        # effect on `calls`.
        calls: list[Any] = []

        class _BridgeSpy(OpenClawMemoryBridge):
            def sync(self, memory_event: Any) -> Any:  # type: ignore[override]
                calls.append(memory_event)
                return super().sync(memory_event)

        install_hooks(host, runtime=runtime, bridge=_BridgeSpy())
        host.fire("agent.user_message", {"turn_id": "t-1", "payload": {"text": "hi"}})
        host.fire("agent.before_tool", {"turn_id": "t-1", "payload": {}})
        assert calls == []

    def test_memory_event_with_flat_payload_falls_back(self) -> None:
        """Toy hosts emit memory events without the ``payload`` envelope.
        The bridge consumes the raw dict in that case."""
        host = FakeHost()
        runtime = _build_runtime()
        _seed_concern(runtime, "c-flat")
        store = runtime.dcn_store
        bridge = OpenClawMemoryBridge(dcn_store=store)
        install_hooks(host, runtime=runtime, bridge=bridge)
        host.fire(
            "agent.memory_write",
            # No outer "payload" envelope and no "event_name".
            {"key": "flat.k", "concern_id": "c-flat"},
        )
        log = list(store.activation_log(concern_id="c-flat"))
        assert len(log) == 1


# ---------------------------------------------------------------------------
# InstalledHooks.uninstall
# ---------------------------------------------------------------------------


class TestUninstall:
    def test_uninstall_calls_every_unsubscribe(self) -> None:
        host = FakeHost()
        installed = install_hooks(host, runtime=_build_runtime())
        installed.uninstall()
        assert installed.is_installed is False
        # Every subscribed callback should have been removed.
        assert all(len(cbs) == 0 for cbs in host.subscriptions.values())
        # And unsubscribe should have run once per subscription.
        assert host.unsubscribe_count == len(OpenClawEventName)

    def test_uninstall_is_idempotent(self) -> None:
        host = FakeHost()
        installed = install_hooks(host, runtime=_build_runtime())
        installed.uninstall()
        installed.uninstall()  # second call no-ops
        assert host.unsubscribe_count == len(OpenClawEventName)

    def test_events_fired_after_uninstall_are_no_op(self) -> None:
        host = FakeHost()
        runtime = _build_runtime()
        _seed_concern(runtime, "c-x")
        bridge = OpenClawMemoryBridge(dcn_store=runtime.dcn_store)
        installed = install_hooks(host, runtime=runtime, bridge=bridge)
        installed.uninstall()
        # No registered callbacks → fire is a no-op.
        host.fire(
            "agent.memory_write",
            {"payload": {"key": "k", "concern_id": "c-x"}},
        )
        assert list(runtime.dcn_store.activation_log(concern_id="c-x")) == []
