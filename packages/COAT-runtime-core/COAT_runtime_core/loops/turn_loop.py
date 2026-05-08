"""Turn Loop — synchronous, returns a :class:`ConcernInjection`.

Sequence (v0.1 §22.1):

    joinpoint event
        → candidate scan       (matcher per concern in the store)
        → coordinate           (rank · resolve · budget · top-K)
        → advice generate      (one Advice per active concern)
        → weave                (build ConcernInjection)
        → log activations      (telemetry into the DCN)
        → emit observer events
        → return injection

Design notes
------------
* The loop is **stateless across turns** — any cross-turn memory (history,
  decay, conflicts) lives in the stores. This keeps the loop trivially
  thread-safe per turn while still being driven by long-lived state.
* A concern with **no** :class:`Pointcut` is treated as inactive on this
  joinpoint; it can still surface via the event/heartbeat loops or via
  explicit upserts. We never silently activate a concern that did not
  declare *some* match condition.
* The matcher is only invoked for concerns with a pointcut, and only its
  ``score`` is fed into the coordinator — the reasons / metadata are
  reserved for the observer side-channel so wire formats stay narrow.
* DCN activation logging is **best-effort**: the DCN store may be wired
  to a backend that rejects unknown nodes; we add the node first
  (idempotent) and only catch ``KeyError`` to keep the turn loop
  resilient if the host wired in a stricter store.
* The loop returns ``None`` *only* when the matcher produced zero
  candidates *and* the host explicitly opted into the
  ``return_none_when_empty`` flag. The default is to return an empty
  :class:`ConcernInjection` so downstream code never has to special-case
  the no-op path.
"""

from __future__ import annotations

from typing import Any

from COAT_runtime_protocol import (
    Advice,
    Concern,
    ConcernInjection,
    ConcernVector,
    JoinpointEvent,
)

from ..config import RuntimeConfig
from ..coordinator import ConcernCoordinator
from ..ports import (
    AdvicePlugin,
    ConcernStore,
    DCNStore,
    MatcherPlugin,
    Observer,
)
from ..ports.observer import NullObserver
from ..weaving import ConcernWeaver


class TurnLoop:
    """Drive a single joinpoint through the full match → weave pipeline."""

    def __init__(
        self,
        *,
        config: RuntimeConfig,
        concern_store: ConcernStore,
        dcn_store: DCNStore,
        matcher: MatcherPlugin,
        coordinator: ConcernCoordinator,
        weaver: ConcernWeaver,
        advice_plugin: AdvicePlugin,
        observer: Observer | None = None,
    ) -> None:
        self._config = config
        self._concern_store = concern_store
        self._dcn_store = dcn_store
        self._matcher = matcher
        self._coordinator = coordinator
        self._weaver = weaver
        self._advice_plugin = advice_plugin
        self._observer = observer or NullObserver()
        self._last_vector: ConcernVector | None = None
        self._last_injection: ConcernInjection | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        joinpoint: JoinpointEvent,
        *,
        context: dict[str, Any] | None = None,
        return_none_when_empty: bool = False,
    ) -> ConcernInjection | None:
        turn_id = self._mint_turn_id(joinpoint)
        ctx = self._build_context(joinpoint, context)

        with self._observer.on_span(
            "COAT.turn",
            turn_id=turn_id,
            joinpoint=joinpoint.name,
        ):
            candidates = list(self._scan_candidates(joinpoint, ctx))
            self._observer.on_metric(
                "COAT.turn.candidates",
                float(len(candidates)),
                joinpoint=joinpoint.name,
            )

            if not candidates and return_none_when_empty:
                self._last_vector = None
                self._last_injection = None
                return None

            vector = self._coordinator.coordinate(
                turn_id=turn_id,
                candidates=candidates,
                joinpoint=joinpoint,
                context=ctx,
            )
            self._last_vector = vector

            advices = self._generate_advices(vector, ctx)
            concerns = {c.id: c for c, _ in candidates}
            injection = self._weaver.build(
                turn_id=turn_id,
                vector=vector,
                concerns=concerns,
                advices=advices,
            )
            self._last_injection = injection

            self._record_activations(joinpoint, vector, concerns)
            self._emit_telemetry(joinpoint, vector, injection)

            return injection

    # ------------------------------------------------------------------
    # Read-only views (for the facade's introspection helpers)
    # ------------------------------------------------------------------

    @property
    def last_vector(self) -> ConcernVector | None:
        return self._last_vector

    @property
    def last_injection(self) -> ConcernInjection | None:
        return self._last_injection

    # ------------------------------------------------------------------
    # Internal — candidate scan
    # ------------------------------------------------------------------

    def _scan_candidates(
        self,
        joinpoint: JoinpointEvent,
        context: dict[str, Any],
    ) -> list[tuple[Concern, float]]:
        # We materialise the iterator into a list so a slow / lazy backend
        # cannot stall the loop mid-pipeline. ConcernStore.iter_all is
        # documented as cheap; if a future backend changes that, the
        # observer metric below makes the cost visible.
        scanned: list[tuple[Concern, float]] = []
        for concern in self._concern_store.iter_all():
            if concern.pointcut is None:
                continue
            try:
                result = self._matcher.match(concern.pointcut, joinpoint, context)
            except Exception as exc:
                self._observer.on_log(
                    "warning",
                    "matcher raised; treating as miss",
                    concern_id=concern.id,
                    error=repr(exc),
                )
                continue
            if not result.matched:
                continue
            scanned.append((concern, float(result.score)))
        return scanned

    # ------------------------------------------------------------------
    # Internal — advice generation
    # ------------------------------------------------------------------

    def _generate_advices(
        self,
        vector: ConcernVector,
        context: dict[str, Any],
    ) -> dict[str, Advice]:
        advices: dict[str, Advice] = {}
        for active in vector.active_concerns:
            concern = self._concern_store.get(active.concern_id)
            if concern is None:
                # The store may have evicted the concern between scan
                # and weave; weaver tolerates a missing entry.
                self._observer.on_log(
                    "warning",
                    "active concern vanished from store between scan and weave",
                    concern_id=active.concern_id,
                )
                continue
            try:
                advices[active.concern_id] = self._advice_plugin.generate(concern, context)
            except Exception as exc:
                # take down the turn; the concern is simply skipped by the weaver.
                self._observer.on_log(
                    "error",
                    "advice plugin raised; skipping concern",
                    concern_id=active.concern_id,
                    error=repr(exc),
                )
        return advices

    # ------------------------------------------------------------------
    # Internal — DCN telemetry
    # ------------------------------------------------------------------

    def _record_activations(
        self,
        joinpoint: JoinpointEvent,
        vector: ConcernVector,
        concerns: dict[str, Concern],
    ) -> None:
        for active in vector.active_concerns:
            concern = concerns.get(active.concern_id)
            if concern is None:
                continue
            # add_node is idempotent (last write wins); doing it before
            # log_activation lets the in-memory DCN store, which rejects
            # unknown node references, accept the activation cleanly.
            try:
                self._dcn_store.add_node(concern)
            except Exception as exc:
                self._observer.on_log(
                    "warning",
                    "DCN add_node failed; skipping activation log",
                    concern_id=concern.id,
                    error=repr(exc),
                )
                continue
            try:
                self._dcn_store.log_activation(
                    concern_id=concern.id,
                    joinpoint_id=joinpoint.id,
                    score=float(active.activation_score),
                    ts=vector.ts,
                )
            except Exception as exc:
                self._observer.on_log(
                    "warning",
                    "DCN log_activation failed",
                    concern_id=concern.id,
                    error=repr(exc),
                )

    # ------------------------------------------------------------------
    # Internal — observer events
    # ------------------------------------------------------------------

    def _emit_telemetry(
        self,
        joinpoint: JoinpointEvent,
        vector: ConcernVector,
        injection: ConcernInjection,
    ) -> None:
        self._observer.on_metric(
            "COAT.turn.active_concerns",
            float(len(vector.active_concerns)),
            joinpoint=joinpoint.name,
        )
        self._observer.on_metric(
            "COAT.turn.injection_tokens",
            float(injection.totals.tokens),
            joinpoint=joinpoint.name,
        )
        self._observer.on_metric(
            "COAT.turn.injection_advices",
            float(injection.totals.advice_count),
            joinpoint=joinpoint.name,
        )
        for escalation in self._coordinator.last_escalations:
            self._observer.on_log(
                "warning",
                "concern escalation emitted",
                **{k: str(v) for k, v in escalation.items()},
            )

    # ------------------------------------------------------------------
    # Internal — helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _mint_turn_id(jp: JoinpointEvent) -> str:
        # If the host already minted a turn id we reuse it so traces
        # stitch together; otherwise we derive one from the joinpoint id
        # so the value is reproducible.
        return jp.turn_id or f"turn-{jp.id}"

    @staticmethod
    def _build_context(
        jp: JoinpointEvent,
        extra: dict[str, Any] | None,
    ) -> dict[str, Any]:
        ctx: dict[str, Any] = {}
        if jp.payload:
            ctx.update(jp.payload)
        if extra:
            ctx.update(extra)
        # Stable bookkeeping keys callers can lean on without poking the
        # JoinpointEvent again.
        ctx.setdefault("joinpoint", jp.name)
        ctx.setdefault("joinpoint_id", jp.id)
        if jp.turn_id is not None:
            ctx.setdefault("turn_id", jp.turn_id)
        return ctx


__all__ = ["TurnLoop"]
