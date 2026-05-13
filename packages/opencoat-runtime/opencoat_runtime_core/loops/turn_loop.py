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
* Context passed to collaborators is ``payload ∪ extra`` with explicit-arg
  precedence for ordinary keys. ``turn_id`` is an exception: after the merge
  it is **forced** to the canonical mint (same string as
  ``ConcernInjection.turn_id``) so payload/context cannot shadow it.
"""

from __future__ import annotations

from typing import Any

from opencoat_runtime_protocol import (
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
        ctx = self._build_context(joinpoint, context, turn_id=turn_id)

        with self._observer.on_span(
            "opencoat.turn",
            turn_id=turn_id,
            joinpoint=joinpoint.name,
        ):
            candidates = list(self._scan_candidates(joinpoint, ctx))
            self._observer.on_metric(
                "opencoat.turn.candidates",
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

            self._record_activations(joinpoint, vector, injection)
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
        injection: ConcernInjection,
    ) -> None:
        # Activation logging is driven by what *actually reached the host*
        # (i.e. survived advice generation + the weaver's budget cutoff),
        # not by the coordinator's intermediate vector. Two reasons:
        #
        #   1. A concern that was active in the vector but lost its
        #      advice (eviction race, plugin error) or got trimmed by
        #      the weaver budget never influenced the host — logging it
        #      would create a "phantom" activation that distorts the
        #      ``history`` pointcut strategy on subsequent turns.
        #   2. Re-fetching the concern from the store (rather than
        #      trusting the candidate-scan snapshot) guarantees we never
        #      ``add_node`` a Concern the host has since deleted. Without
        #      this, the eviction race would silently revive deleted
        #      DCN nodes.
        if not injection.injections:
            return

        scores = {a.concern_id: a.activation_score for a in vector.active_concerns}
        for cid in _unique_concern_ids(injection):
            concern = self._concern_store.get(cid)
            if concern is None:
                # The concern made it into the injection (so it was alive
                # at advice-generation time) but has since been deleted.
                # Skip the DCN write — don't resurrect a deleted node.
                self._observer.on_log(
                    "warning",
                    "concern in injection vanished from store; activation skipped",
                    concern_id=cid,
                )
                continue
            try:
                # Idempotent — refreshes the in-store snapshot in case
                # the host upserted in between.
                self._dcn_store.add_node(concern)
            except Exception as exc:
                self._observer.on_log(
                    "warning",
                    "DCN add_node failed; skipping activation log",
                    concern_id=cid,
                    error=repr(exc),
                )
                continue
            try:
                self._dcn_store.log_activation(
                    concern_id=cid,
                    joinpoint_id=joinpoint.id,
                    score=float(scores.get(cid, 0.0)),
                    ts=vector.ts,
                )
            except Exception as exc:
                self._observer.on_log(
                    "warning",
                    "DCN log_activation failed",
                    concern_id=cid,
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
            "opencoat.turn.active_concerns",
            float(len(vector.active_concerns)),
            joinpoint=joinpoint.name,
        )
        self._observer.on_metric(
            "opencoat.turn.injection_tokens",
            float(injection.totals.tokens),
            joinpoint=joinpoint.name,
        )
        self._observer.on_metric(
            "opencoat.turn.injection_advices",
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
        *,
        turn_id: str,
    ) -> dict[str, Any]:
        ctx: dict[str, Any] = {}
        if jp.payload:
            ctx.update(jp.payload)
        if extra:
            ctx.update(extra)
        # Stable bookkeeping keys callers can lean on without poking the
        # JoinpointEvent again.
        #
        # ``turn_id`` is assigned **after** merging payload + caller context
        # so it always matches ``ConcernInjection.turn_id``. Payload keys or
        # ``context=`` entries named ``turn_id`` cannot shadow the runtime
        # mint — otherwise matcher/advice telemetry drifts from the wire id.
        ctx.setdefault("joinpoint", jp.name)
        ctx.setdefault("joinpoint_id", jp.id)
        ctx["turn_id"] = turn_id
        return ctx


def _unique_concern_ids(injection: ConcernInjection) -> list[str]:
    """Return the distinct concern ids in ``injection.injections`` in
    first-seen order. Multiple advices may share a concern (today the
    weaver emits one each, but the contract permits more); we want to
    log each concern's activation exactly once."""
    seen: list[str] = []
    seen_set: set[str] = set()
    for inj in injection.injections:
        if inj.concern_id in seen_set:
            continue
        seen_set.add(inj.concern_id)
        seen.append(inj.concern_id)
    return seen


__all__ = ["TurnLoop"]
