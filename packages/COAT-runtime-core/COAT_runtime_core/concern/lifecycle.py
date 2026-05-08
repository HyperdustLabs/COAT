"""Concern Lifecycle Manager — v0.1 §20.12 (M2 PR-11).

Owns the (lifecycle_state, activation_state, metrics, updated_at)
quartet of every persisted :class:`Concern`. The manager is the
**only** path that mutates ``Concern.lifecycle_state`` once a concern
has been admitted to the store; everything else (the coordinator,
the weaver, the verifier) reads.

State machine
-------------

::

    created ──► active ◄──► reinforced
                  ▲    │
                  │    ▼
                  └── weakened
                  │
                  ├──► merged ──► archived ──► revived ──► active
                  ├──► frozen ──► active
                  └──► archived ──► revived ──► active
                                  │
                                  └──► deleted   (terminal)

The matrix in :data:`_ALLOWED_TRANSITIONS` encodes the full
generalisation; the four named methods (``reinforce`` / ``weaken``
/ ``archive`` / ``revive``) are convenience wrappers around the
generic :meth:`transition` for the by-far-most-common operations.

Design constraints
------------------

* **Store is the source of truth.** Every public method re-fetches
  the concern from :class:`ConcernStore` before mutating, so a stale
  caller-side snapshot can't silently overwrite newer state. The
  caller's :class:`Concern` is only used for its ``id``.
* **DCN sync.** Transitions that affect graph reachability
  (``archive``) propagate to :class:`DCNStore` via the dedicated
  port methods. The Concern node remains in the DCN so existing
  edges are preserved — only its ``lifecycle_state`` flips.
* **Determinism.** A ``now`` callable is injectable for tests; the
  default is :func:`datetime.now(UTC)`.
* **Idempotent terminals.** ``archive`` of an already-archived
  concern, or ``transition`` to the current state for an idempotent
  state, is a no-op (returns the stored snapshot unchanged, no
  ``updated_at`` bump). For score-changing methods (reinforce /
  weaken) the same-lifecycle case still applies the score delta —
  that's the point.
* **Hard-stop on terminal.** Any transition out of ``DELETED`` raises
  :class:`InvalidLifecycleTransition` so a use-after-delete bug
  fails loud instead of silently resurrecting state.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime

from COAT_runtime_protocol import (
    ActivationState,
    Concern,
    ConcernMetrics,
    LifecycleState,
)

from ..ports import ConcernStore, DCNStore
from ..types import ConcernId

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class InvalidLifecycleTransition(ValueError):
    """Raised when a requested transition isn't allowed by the matrix.

    Subclass of :class:`ValueError` so callers that don't care about
    the specific failure mode can ``except ValueError`` and move on.
    """


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------


_LS = LifecycleState

# Canonical transition matrix. Values are the set of states reachable
# in one step from each key. Self-loops are included for the states
# where staying is meaningful (REINFORCED + REINFORCED still wants to
# bump the score; ARCHIVED + ARCHIVED is an idempotent re-archive).
_ALLOWED_TRANSITIONS: dict[LifecycleState, frozenset[LifecycleState]] = {
    _LS.CREATED: frozenset(
        {_LS.ACTIVE, _LS.REINFORCED, _LS.WEAKENED, _LS.FROZEN, _LS.ARCHIVED, _LS.DELETED}
    ),
    _LS.ACTIVE: frozenset(
        {
            _LS.ACTIVE,
            _LS.REINFORCED,
            _LS.WEAKENED,
            _LS.MERGED,
            _LS.FROZEN,
            _LS.ARCHIVED,
            _LS.DELETED,
        }
    ),
    _LS.REINFORCED: frozenset(
        {
            _LS.ACTIVE,
            _LS.REINFORCED,
            _LS.WEAKENED,
            _LS.MERGED,
            _LS.FROZEN,
            _LS.ARCHIVED,
            _LS.DELETED,
        }
    ),
    _LS.WEAKENED: frozenset(
        {
            _LS.ACTIVE,
            _LS.REINFORCED,
            _LS.WEAKENED,
            _LS.FROZEN,
            _LS.ARCHIVED,
            _LS.DELETED,
        }
    ),
    _LS.MERGED: frozenset({_LS.ARCHIVED, _LS.DELETED}),
    _LS.FROZEN: frozenset({_LS.ACTIVE, _LS.FROZEN, _LS.ARCHIVED, _LS.DELETED}),
    _LS.ARCHIVED: frozenset({_LS.ARCHIVED, _LS.REVIVED, _LS.DELETED}),
    _LS.REVIVED: frozenset({_LS.ACTIVE, _LS.REINFORCED, _LS.WEAKENED, _LS.ARCHIVED, _LS.DELETED}),
    # DELETED is truly terminal — no resurrection without a fresh
    # ``upsert`` of a brand-new concern. revive() is for ARCHIVED.
    _LS.DELETED: frozenset(),
}


# Lifecycle states from which reinforce / weaken are allowed. Frozen
# concerns must be explicitly thawed (transition to ACTIVE) before
# their score can move; merged / archived / deleted ones cannot have
# their score moved without first reviving.
_REINFORCE_FROM: frozenset[LifecycleState] = frozenset(
    {_LS.CREATED, _LS.ACTIVE, _LS.REINFORCED, _LS.WEAKENED, _LS.REVIVED}
)
_WEAKEN_FROM: frozenset[LifecycleState] = _REINFORCE_FROM


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clamp01(value: float) -> float:
    if value <= 0.0:
        return 0.0
    if value >= 1.0:
        return 1.0
    return float(value)


def _coerce_state(raw: LifecycleState | str) -> LifecycleState:
    """Round-trip a stored ``lifecycle_state`` (str, due to
    ``use_enum_values=True``) back to the enum for matrix lookup."""
    if isinstance(raw, LifecycleState):
        return raw
    return LifecycleState(raw)


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------


class ConcernLifecycleManager:
    """State-machine manager for Concern lifecycle.

    Reads the canonical Concern from ``concern_store``, applies the
    requested transition, persists, and returns the new snapshot.
    DCN-resident state stays in sync for graph-affecting transitions.

    Parameters
    ----------
    concern_store:
        The :class:`ConcernStore` to read from / write to. Must
        contain the concern being mutated; use-before-upsert raises
        :class:`KeyError`.
    dcn_store:
        The :class:`DCNStore` for graph-affecting transitions
        (currently just ``archive``).
    now:
        Optional clock injected for deterministic tests. Defaults to
        ``datetime.now(UTC)``.
    reinforce_delta:
        Default amount added to ``activation_state.score`` per
        :meth:`reinforce` call when no ``delta`` is passed.
    weaken_delta:
        Default amount subtracted from ``activation_state.score``
        per :meth:`weaken` call when no ``delta`` is passed.
    initial_score:
        Score assumed for a concern that has never been activated
        before (``activation_state is None`` or
        ``activation_state.score is None``). The first
        :meth:`reinforce` then bumps from this baseline.
    """

    DEFAULT_REINFORCE_DELTA: float = 0.1
    DEFAULT_WEAKEN_DELTA: float = 0.1
    DEFAULT_INITIAL_SCORE: float = 0.5

    def __init__(
        self,
        *,
        concern_store: ConcernStore,
        dcn_store: DCNStore,
        now: Callable[[], datetime] | None = None,
        reinforce_delta: float | None = None,
        weaken_delta: float | None = None,
        initial_score: float | None = None,
    ) -> None:
        self._concern_store = concern_store
        self._dcn_store = dcn_store
        self._now = now if now is not None else (lambda: datetime.now(UTC))
        self._reinforce_delta = (
            reinforce_delta if reinforce_delta is not None else self.DEFAULT_REINFORCE_DELTA
        )
        self._weaken_delta = weaken_delta if weaken_delta is not None else self.DEFAULT_WEAKEN_DELTA
        self._initial_score = (
            initial_score if initial_score is not None else self.DEFAULT_INITIAL_SCORE
        )
        if not 0.0 <= self._reinforce_delta <= 1.0:
            raise ValueError(
                f"reinforce_delta must be in [0.0, 1.0]; got {self._reinforce_delta!r}"
            )
        if not 0.0 <= self._weaken_delta <= 1.0:
            raise ValueError(f"weaken_delta must be in [0.0, 1.0]; got {self._weaken_delta!r}")
        if not 0.0 <= self._initial_score <= 1.0:
            raise ValueError(f"initial_score must be in [0.0, 1.0]; got {self._initial_score!r}")

    # ------------------------------------------------------------------
    # Public API — convenience wrappers
    # ------------------------------------------------------------------

    def reinforce(self, concern: Concern, delta: float | None = None) -> Concern:
        """Bump score, set ``lifecycle_state`` to ``reinforced``.

        Increments ``activation_state.score`` by ``delta`` (clamped
        to ``[0, 1]``), updates ``last_activated_at``, resets
        ``decay`` to ``0``, sets ``active=True``, and bumps
        ``metrics.activations``. Allowed from
        ``{created, active, reinforced, weakened, revived}``.
        """
        amount = self._reinforce_delta if delta is None else delta
        if not 0.0 <= amount <= 1.0:
            raise ValueError(f"delta must be in [0.0, 1.0]; got {amount!r}")
        # ``is_reinforcement=True`` is what makes this an activation
        # event for the purposes of metrics + activation_state — NOT
        # the sign of ``score_delta``. ``delta=0.0`` is a legitimate
        # call (record an activation without biasing the score) and
        # must still bump ``metrics.activations`` + reset decay +
        # set ``active=True`` (Codex P2 on PR-11).
        return self._mutate(
            concern,
            target=_LS.REINFORCED,
            from_states=_REINFORCE_FROM,
            score_delta=+amount,
            is_reinforcement=True,
            deactivate=False,
            sync_dcn_archive=False,
            action="reinforce",
            reason="",
        )

    def weaken(self, concern: Concern, delta: float | None = None) -> Concern:
        """Drop score, set ``lifecycle_state`` to ``weakened``.

        Decrements ``activation_state.score`` by ``delta`` (clamped
        to ``[0, 1]``) and updates ``updated_at`` / ``last_activated_at``.
        Does **not** touch ``metrics.activations`` — a weakening
        signal is not an activation. Allowed from the same set as
        :meth:`reinforce`.
        """
        amount = self._weaken_delta if delta is None else delta
        if not 0.0 <= amount <= 1.0:
            raise ValueError(f"delta must be in [0.0, 1.0]; got {amount!r}")
        return self._mutate(
            concern,
            target=_LS.WEAKENED,
            from_states=_WEAKEN_FROM,
            score_delta=-amount,
            is_reinforcement=False,
            deactivate=False,
            sync_dcn_archive=False,
            action="weaken",
            reason="",
        )

    def archive(self, concern: Concern, *, reason: str = "") -> Concern:
        """Mark the concern archived and propagate to the DCN.

        Idempotent: archiving an already-archived concern returns
        the stored snapshot unchanged (no ``updated_at`` bump).
        Disallowed only from ``deleted``.
        """
        return self._mutate(
            concern,
            target=_LS.ARCHIVED,
            from_states=None,  # rely on the matrix (any non-DELETED → ARCHIVED)
            score_delta=None,
            is_reinforcement=False,
            deactivate=True,
            sync_dcn_archive=True,
            action="archive",
            reason=reason,
        )

    def revive(self, concern: Concern) -> Concern:
        """Bring an archived concern back to the runtime.

        After revive the concern's ``lifecycle_state`` is ``revived``
        — a transient state that the next :meth:`reinforce` flips to
        ``reinforced``. The activation snapshot is reset
        (``active=False``, ``decay=0``) but the historical ``score``
        is preserved so the host doesn't have to re-train signal
        from scratch. Allowed only from ``archived``.
        """
        return self._mutate(
            concern,
            target=_LS.REVIVED,
            from_states=frozenset({_LS.ARCHIVED}),
            score_delta=None,
            is_reinforcement=False,
            deactivate=True,
            sync_dcn_archive=False,
            action="revive",
            reason="",
            reset_decay=True,
        )

    def transition(
        self,
        concern: Concern,
        target: LifecycleState | str,
        *,
        reason: str = "",
    ) -> Concern:
        """Generic transition path.

        Useful for the rarer states (``MERGED``, ``FROZEN``,
        ``DELETED``) and for hosts that want full control over the
        state machine. Routes through the same ``_ALLOWED_TRANSITIONS``
        matrix as the convenience methods, with no extra source-state
        gate beyond the matrix itself.
        """
        target_state = _coerce_state(target)
        deactivate = target_state in {
            _LS.MERGED,
            _LS.FROZEN,
            _LS.ARCHIVED,
            _LS.DELETED,
        }
        sync_archive = target_state == _LS.ARCHIVED
        return self._mutate(
            concern,
            target=target_state,
            from_states=None,
            score_delta=None,
            is_reinforcement=False,
            deactivate=deactivate,
            sync_dcn_archive=sync_archive,
            action="transition",
            reason=reason,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _mutate(
        self,
        concern: Concern,
        *,
        target: LifecycleState,
        from_states: frozenset[LifecycleState] | None,
        score_delta: float | None,
        is_reinforcement: bool,
        deactivate: bool,
        sync_dcn_archive: bool,
        action: str,
        reason: str,
        reset_decay: bool = False,
    ) -> Concern:
        cid: ConcernId = concern.id
        if not cid:
            raise ValueError("Concern.id must be a non-empty string")

        stored = self._concern_store.get(cid)
        if stored is None:
            raise KeyError(f"unknown concern: {cid!r}")

        current = _coerce_state(stored.lifecycle_state)

        # Per-method source-state gate (e.g. ``reinforce`` only from
        # the "alive" subset; ``revive`` only from ``archived``). The
        # matrix below is the wider canonical truth and catches any
        # gap the per-method gate might miss.
        if from_states is not None and current not in from_states:
            raise InvalidLifecycleTransition(
                f"{action}: cannot {action} a {current.value!r} concern "
                f"({cid!r}); allowed source states: "
                f"{sorted(s.value for s in from_states)}"
            )

        # Matrix gate: is ``current → target`` reachable in one step?
        allowed_targets = _ALLOWED_TRANSITIONS.get(current, frozenset())
        if target not in allowed_targets:
            raise InvalidLifecycleTransition(
                f"{action}: cannot transition concern {cid!r} from "
                f"{current.value!r} to {target.value!r}; allowed targets "
                f"from {current.value!r}: "
                f"{sorted(s.value for s in allowed_targets) or '<none — terminal>'}"
            )

        # Idempotent fast path for state-only transitions where the
        # state isn't changing AND there's no score delta to apply.
        # Score-changing methods (reinforce / weaken) always proceed
        # so repeated calls cumulatively move the score.
        if score_delta is None and target == current:
            logger.debug(
                "lifecycle.%s no-op for %s: already in %s%s",
                action,
                cid,
                current.value,
                f" (reason={reason!r})" if reason else "",
            )
            # Still propagate to the DCN if asked — keeps store + DCN
            # convergent even if a previous archive() raced ahead of
            # the DCN write.
            if sync_dcn_archive:
                self._dcn_store.archive(cid)
            return stored

        now = self._now()

        activation = (
            stored.activation_state.model_copy(deep=True)
            if stored.activation_state is not None
            else ActivationState()
        )

        if score_delta is not None:
            old_score = activation.score if activation.score is not None else self._initial_score
            activation.score = _clamp01(old_score + score_delta)
            activation.last_activated_at = now

        # Reinforcement is signalled by ``is_reinforcement``, NOT by
        # ``score_delta > 0``. ``reinforce(c, delta=0.0)`` is a valid
        # call that records an activation event without biasing the
        # score (e.g. host wants a heartbeat ping); it must still
        # reset decay, set ``active=True``, and bump
        # ``metrics.activations`` (Codex P2 on PR-11). Conflating the
        # two would silently drop those calls from analytics and
        # leave the concern in a "reinforced but inactive/cooling"
        # state — a contradiction.
        if is_reinforcement:
            activation.decay = 0.0
            activation.active = True

        if deactivate:
            activation.active = False
        if reset_decay:
            activation.decay = 0.0

        metrics = (
            stored.metrics.model_copy(deep=True) if stored.metrics is not None else ConcernMetrics()
        )
        if is_reinforcement:
            metrics.activations += 1

        updated = stored.model_copy(deep=True)
        updated.lifecycle_state = target.value
        updated.activation_state = activation
        updated.metrics = metrics
        updated.updated_at = now

        persisted = self._concern_store.upsert(updated)

        if sync_dcn_archive:
            self._dcn_store.archive(cid)

        logger.debug(
            "lifecycle.%s %s: %s -> %s%s",
            action,
            cid,
            current.value,
            target.value,
            f" (reason={reason!r})" if reason else "",
        )
        return persisted


__all__ = [
    "ConcernLifecycleManager",
    "InvalidLifecycleTransition",
]
