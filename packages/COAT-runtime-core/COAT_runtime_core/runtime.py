"""Top-level facade: :class:`COATRuntime`.

The facade composes every L2 module and exposes the three loop entrypoints:

* :meth:`on_joinpoint` — turn loop (sync, returns an injection)
* :meth:`on_event`     — event loop (async-friendly, fire-and-forget)
* :meth:`tick`         — heartbeat loop (long-term DCN maintenance)

In M0 every method raises :class:`NotImplementedError`. M1 wires up real
implementations against the in-memory adapters.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from COAT_runtime_protocol import (
    ConcernInjection,
    ConcernVector,
    JoinpointEvent,
)

from .config import RuntimeConfig
from .ports import (
    AdvicePlugin,
    ConcernStore,
    DCNStore,
    Embedder,
    LLMClient,
    MatcherPlugin,
    Observer,
)
from .ports.observer import NullObserver

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# Reports / events at the facade boundary
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RuntimeEvent:
    """Asynchronous, non-turn-critical signal (tool result, env event, …)."""

    type: str
    ts: datetime
    payload: dict


@dataclass(frozen=True)
class HeartbeatReport:
    """Outcome of one heartbeat tick."""

    ts: datetime
    decay_count: int = 0
    merge_count: int = 0
    archive_count: int = 0
    conflict_count: int = 0


@dataclass(frozen=True)
class RuntimeSnapshot:
    """A read-only snapshot for introspection / debugging."""

    ts: datetime
    concern_count: int
    active_concern_count: int
    dcn_node_count: int
    dcn_edge_count: int


# ---------------------------------------------------------------------------
# Facade
# ---------------------------------------------------------------------------


class COATRuntime:
    """Top-level entrypoint that wires the L2 modules together.

    The facade is intentionally thin: it owns the ports and delegates to
    the per-module classes. Hosts and the daemon both go through this
    object — there is no other supported way to drive the runtime.
    """

    def __init__(
        self,
        config: RuntimeConfig | None = None,
        *,
        concern_store: ConcernStore,
        dcn_store: DCNStore,
        llm: LLMClient,
        embedder: Embedder | None = None,
        matcher: MatcherPlugin | None = None,
        advice_plugin: AdvicePlugin | None = None,
        observer: Observer | None = None,
    ) -> None:
        self._config = config or RuntimeConfig()
        self._concern_store = concern_store
        self._dcn_store = dcn_store
        self._llm = llm
        self._embedder = embedder
        self._matcher = matcher
        self._advice_plugin = advice_plugin
        self._observer = observer or NullObserver()

    # --- public API --------------------------------------------------------

    @property
    def config(self) -> RuntimeConfig:
        return self._config

    def on_joinpoint(self, jp: JoinpointEvent) -> ConcernInjection | None:
        """Turn-loop: ingest a joinpoint, return an injection (or None)."""
        raise NotImplementedError("M1 will implement the turn loop.")

    def on_event(self, ev: RuntimeEvent) -> None:
        """Event-loop: enqueue a non-turn-critical event."""
        raise NotImplementedError("M1 will implement the event loop.")

    def tick(self, now: datetime | None = None) -> HeartbeatReport:
        """Heartbeat-loop: drive long-term DCN maintenance."""
        raise NotImplementedError("M1 will implement the heartbeat loop.")

    def current_vector(self) -> ConcernVector | None:
        """Return the most recently-computed Concern Vector, if any."""
        raise NotImplementedError("M1 will track the vector across turns.")

    def snapshot(self) -> RuntimeSnapshot:
        """Cheap, read-only snapshot used by /healthz and the CLI."""
        raise NotImplementedError("M1 will compute snapshots from the stores.")
