"""Hermetic tests for :class:`ConcernLifecycleManager` (M2 PR-11).

The manager has two outside-world dependencies — :class:`ConcernStore`
and :class:`DCNStore` — and one optional clock. We use the in-memory
implementations from ``COAT_runtime_storage`` (already exercised by
their own unit tests) for the stores, and inject a fixed-time
``now`` callable so every timestamp the manager writes is byte-stable.

No real LLM, no real time, no random IDs — every test in this file
runs identically 1000 times in a row.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from COAT_runtime_core.concern.lifecycle import (
    _ALLOWED_TRANSITIONS,
    ConcernLifecycleManager,
    InvalidLifecycleTransition,
    _coerce_state,
)
from COAT_runtime_protocol import (
    ActivationState,
    Concern,
    ConcernKind,
    ConcernMetrics,
    LifecycleState,
)
from COAT_runtime_storage.memory import MemoryConcernStore, MemoryDCNStore

# ---------------------------------------------------------------------------
# Test scaffolding
# ---------------------------------------------------------------------------


_FIXED_NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


def _make_concern(
    *,
    cid: str = "c-test",
    name: str = "test concern",
    lifecycle: LifecycleState | str = LifecycleState.CREATED,
    activation: ActivationState | None = None,
    metrics: ConcernMetrics | None = None,
) -> Concern:
    return Concern(
        id=cid,
        name=name,
        kind=ConcernKind.CONCERN,
        lifecycle_state=lifecycle,
        activation_state=activation,
        metrics=metrics if metrics is not None else ConcernMetrics(),
    )


def _make_manager(
    *,
    now: datetime = _FIXED_NOW,
    seed: list[Concern] | None = None,
    seed_dcn: bool = True,
    **overrides: Any,
) -> tuple[ConcernLifecycleManager, MemoryConcernStore, MemoryDCNStore]:
    cs = MemoryConcernStore()
    ds = MemoryDCNStore()
    if seed:
        for c in seed:
            cs.upsert(c)
            if seed_dcn:
                ds.add_node(c)
    mgr = ConcernLifecycleManager(
        concern_store=cs,
        dcn_store=ds,
        now=lambda: now,
        **overrides,
    )
    return mgr, cs, ds


# ---------------------------------------------------------------------------
# Construction / configuration
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_defaults_persist(self) -> None:
        mgr, _, _ = _make_manager()
        assert mgr._reinforce_delta == ConcernLifecycleManager.DEFAULT_REINFORCE_DELTA
        assert mgr._weaken_delta == ConcernLifecycleManager.DEFAULT_WEAKEN_DELTA
        assert mgr._initial_score == ConcernLifecycleManager.DEFAULT_INITIAL_SCORE

    @pytest.mark.parametrize("kw", ["reinforce_delta", "weaken_delta", "initial_score"])
    def test_rejects_out_of_range_floats(self, kw: str) -> None:
        with pytest.raises(ValueError, match=kw):
            _make_manager(**{kw: 1.5})
        with pytest.raises(ValueError, match=kw):
            _make_manager(**{kw: -0.1})

    def test_unknown_concern_raises_keyerror(self) -> None:
        # Calling any mutator with a Concern that isn't in the store
        # is a programming bug — fail loud, don't silently upsert.
        mgr, _, _ = _make_manager()
        ghost = _make_concern(cid="c-not-in-store")
        with pytest.raises(KeyError, match="c-not-in-store"):
            mgr.reinforce(ghost)
        with pytest.raises(KeyError, match="c-not-in-store"):
            mgr.weaken(ghost)
        with pytest.raises(KeyError, match="c-not-in-store"):
            mgr.archive(ghost)
        with pytest.raises(KeyError, match="c-not-in-store"):
            mgr.revive(ghost)


# ---------------------------------------------------------------------------
# State machine matrix
# ---------------------------------------------------------------------------


class TestStateMachine:
    def test_deleted_is_terminal(self) -> None:
        # DELETED has zero outgoing edges — anything else is a
        # use-after-delete bug and the matrix needs to keep flagging
        # it loudly.
        assert _ALLOWED_TRANSITIONS[LifecycleState.DELETED] == frozenset()

    def test_archive_is_idempotent_in_matrix(self) -> None:
        assert LifecycleState.ARCHIVED in _ALLOWED_TRANSITIONS[LifecycleState.ARCHIVED]

    def test_revive_only_from_archived(self) -> None:
        # Only ARCHIVED can transition to REVIVED — the manager's
        # revive() guard pins this even tighter, but the underlying
        # matrix should agree.
        for state, allowed in _ALLOWED_TRANSITIONS.items():
            if state == LifecycleState.ARCHIVED:
                assert LifecycleState.REVIVED in allowed
            else:
                assert LifecycleState.REVIVED not in allowed

    def test_no_dangling_states(self) -> None:
        # Every enum value is a key in the matrix (no silent gap that
        # would let a fresh state emerge unsupported).
        keys = set(_ALLOWED_TRANSITIONS.keys())
        assert keys == set(LifecycleState)

    def test_coerce_state_round_trips_strings(self) -> None:
        assert _coerce_state(LifecycleState.ARCHIVED) is LifecycleState.ARCHIVED
        assert _coerce_state("archived") is LifecycleState.ARCHIVED


# ---------------------------------------------------------------------------
# reinforce()
# ---------------------------------------------------------------------------


class TestReinforce:
    def test_first_reinforce_seeds_from_initial_score(self) -> None:
        # No activation_state on the stored concern → first reinforce
        # bumps from the configured baseline (0.5) by the default
        # delta (0.1) → 0.6.
        c = _make_concern()
        mgr, _, _ = _make_manager(seed=[c])
        out = mgr.reinforce(c)
        assert out.activation_state is not None
        assert out.activation_state.score == pytest.approx(0.6)
        assert out.activation_state.active is True
        assert out.activation_state.last_activated_at == _FIXED_NOW
        assert out.activation_state.decay == 0.0
        assert out.lifecycle_state == "reinforced"
        assert out.metrics.activations == 1
        assert out.updated_at == _FIXED_NOW

    def test_repeated_reinforce_accumulates_score_and_activations(self) -> None:
        c = _make_concern()
        mgr, _, _ = _make_manager(seed=[c])
        a = mgr.reinforce(c, delta=0.2)  # 0.5 + 0.2 = 0.7
        b = mgr.reinforce(a, delta=0.2)  # 0.7 + 0.2 = 0.9
        assert b.activation_state.score == pytest.approx(0.9)
        assert b.metrics.activations == 2

    def test_reinforce_clamps_at_one(self) -> None:
        c = _make_concern()
        mgr, _, _ = _make_manager(seed=[c])
        out = mgr.reinforce(c, delta=1.0)
        assert out.activation_state.score == pytest.approx(1.0)
        # Pushing again must not overflow.
        out2 = mgr.reinforce(out, delta=0.5)
        assert out2.activation_state.score == pytest.approx(1.0)

    def test_reinforce_resets_decay(self) -> None:
        c = _make_concern(activation=ActivationState(score=0.4, decay=0.3))
        mgr, _, _ = _make_manager(seed=[c])
        out = mgr.reinforce(c, delta=0.1)
        assert out.activation_state.decay == 0.0

    @pytest.mark.parametrize("bad", [-0.1, 1.5])
    def test_reinforce_rejects_out_of_range_delta(self, bad: float) -> None:
        c = _make_concern()
        mgr, _, _ = _make_manager(seed=[c])
        with pytest.raises(ValueError, match="delta"):
            mgr.reinforce(c, delta=bad)

    def test_reinforce_blocked_from_archived(self) -> None:
        # ARCHIVED concerns must be revived first; reinforce-on-archive
        # is a programming bug and should fail loud.
        c = _make_concern(lifecycle=LifecycleState.ARCHIVED)
        mgr, _, _ = _make_manager(seed=[c])
        with pytest.raises(InvalidLifecycleTransition, match="archived"):
            mgr.reinforce(c)

    def test_reinforce_blocked_from_deleted(self) -> None:
        c = _make_concern(lifecycle=LifecycleState.DELETED)
        mgr, _, _ = _make_manager(seed=[c])
        with pytest.raises(InvalidLifecycleTransition):
            mgr.reinforce(c)

    def test_reinforce_persists_to_store(self) -> None:
        # The returned snapshot is one thing; verify the store is
        # actually mutated (callers reading via store.get must see
        # the new state).
        c = _make_concern()
        mgr, cs, _ = _make_manager(seed=[c])
        mgr.reinforce(c)
        stored = cs.get(c.id)
        assert stored is not None
        assert stored.lifecycle_state == "reinforced"
        assert stored.activation_state.score == pytest.approx(0.6)


# ---------------------------------------------------------------------------
# weaken()
# ---------------------------------------------------------------------------


class TestWeaken:
    def test_weaken_subtracts_from_initial_score(self) -> None:
        c = _make_concern()
        mgr, _, _ = _make_manager(seed=[c])
        out = mgr.weaken(c)
        # 0.5 - 0.1 = 0.4
        assert out.activation_state.score == pytest.approx(0.4)
        assert out.lifecycle_state == "weakened"
        assert out.activation_state.last_activated_at == _FIXED_NOW
        assert out.updated_at == _FIXED_NOW

    def test_weaken_does_not_bump_activations(self) -> None:
        # A weakening signal is NOT an activation — the metric tracks
        # how often the concern fired, not how often the host poked
        # at it. Pinning this so a future refactor doesn't conflate.
        c = _make_concern(metrics=ConcernMetrics(activations=3))
        mgr, _, _ = _make_manager(seed=[c])
        out = mgr.weaken(c)
        assert out.metrics.activations == 3

    def test_weaken_clamps_at_zero(self) -> None:
        c = _make_concern(activation=ActivationState(score=0.05))
        mgr, _, _ = _make_manager(seed=[c])
        out = mgr.weaken(c, delta=0.5)
        assert out.activation_state.score == pytest.approx(0.0)

    def test_weaken_does_not_reset_decay(self) -> None:
        # Weakening is a "let it cool" signal — keep accumulated
        # decay so a follow-up sweeper can archive cold concerns.
        c = _make_concern(activation=ActivationState(score=0.7, decay=0.2))
        mgr, _, _ = _make_manager(seed=[c])
        out = mgr.weaken(c, delta=0.1)
        assert out.activation_state.decay == pytest.approx(0.2)

    def test_weaken_preserves_active_flag(self) -> None:
        # Unlike archive(), weaken() is not a deactivation — the
        # concern is still in play, just less prominently.
        c = _make_concern(activation=ActivationState(score=0.7, active=True))
        mgr, _, _ = _make_manager(seed=[c])
        out = mgr.weaken(c)
        assert out.activation_state.active is True


# ---------------------------------------------------------------------------
# archive() + DCN sync
# ---------------------------------------------------------------------------


class TestArchive:
    def test_archive_flips_lifecycle_and_deactivates(self) -> None:
        c = _make_concern(
            lifecycle=LifecycleState.ACTIVE,
            activation=ActivationState(score=0.8, active=True),
        )
        mgr, _, _ = _make_manager(seed=[c])
        out = mgr.archive(c, reason="superseded")
        assert out.lifecycle_state == "archived"
        assert out.activation_state.active is False
        # Score is preserved so the host can revive without losing
        # signal — only ``active`` flips.
        assert out.activation_state.score == pytest.approx(0.8)
        assert out.updated_at == _FIXED_NOW

    def test_archive_propagates_to_dcn(self) -> None:
        c = _make_concern(lifecycle=LifecycleState.ACTIVE)
        mgr, _, ds = _make_manager(seed=[c])
        mgr.archive(c)
        node = ds.get_node(c.id)
        assert node is not None
        assert node.lifecycle_state == "archived"

    def test_archive_idempotent(self) -> None:
        c = _make_concern(lifecycle=LifecycleState.ARCHIVED)
        mgr, cs, _ = _make_manager(seed=[c])
        before = cs.get(c.id)
        out = mgr.archive(c)
        assert out.lifecycle_state == "archived"
        # ``updated_at`` must NOT bump on idempotent re-archive — the
        # store didn't change, so the timestamp shouldn't lie.
        assert out.updated_at == before.updated_at

    def test_archive_idempotent_still_syncs_dcn(self) -> None:
        # Edge case: store says "archived" but the DCN never got the
        # memo (e.g. earlier process crash between upsert and
        # dcn.archive). Re-archiving should still flip the DCN node
        # so the two stores reconverge.
        c = _make_concern(lifecycle=LifecycleState.ARCHIVED)
        mgr, _, ds = _make_manager(seed=[c])
        # Pretend the DCN is out of sync — node says ACTIVE.
        node = ds.get_node(c.id)
        assert node is not None
        # Force the DCN copy back to "active" so we can see the
        # idempotent archive heal it.
        ds.add_node(_make_concern(cid=c.id, lifecycle=LifecycleState.ACTIVE))
        mgr.archive(c)
        healed = ds.get_node(c.id)
        assert healed is not None
        assert healed.lifecycle_state == "archived"

    def test_archive_blocked_from_deleted(self) -> None:
        c = _make_concern(lifecycle=LifecycleState.DELETED)
        mgr, _, _ = _make_manager(seed=[c])
        with pytest.raises(InvalidLifecycleTransition):
            mgr.archive(c)


# ---------------------------------------------------------------------------
# revive()
# ---------------------------------------------------------------------------


class TestRevive:
    def test_revive_only_from_archived(self) -> None:
        # ACTIVE → revive is a programming error; revive is for
        # bringing a concern out of the archive, not for "refresh".
        c = _make_concern(lifecycle=LifecycleState.ACTIVE)
        mgr, _, _ = _make_manager(seed=[c])
        with pytest.raises(InvalidLifecycleTransition, match="active"):
            mgr.revive(c)

    def test_revive_resets_active_and_decay_keeps_score(self) -> None:
        c = _make_concern(
            lifecycle=LifecycleState.ARCHIVED,
            activation=ActivationState(score=0.7, active=False, decay=0.4),
        )
        mgr, _, _ = _make_manager(seed=[c])
        out = mgr.revive(c)
        assert out.lifecycle_state == "revived"
        # Active should remain False — revive makes the concern
        # eligible, not currently firing. The next reinforce flips it.
        assert out.activation_state.active is False
        assert out.activation_state.decay == 0.0
        # Historical score is intact — the host doesn't have to
        # rebuild signal from scratch.
        assert out.activation_state.score == pytest.approx(0.7)

    def test_revive_then_reinforce_returns_to_reinforced(self) -> None:
        c = _make_concern(
            lifecycle=LifecycleState.ARCHIVED,
            activation=ActivationState(score=0.6),
        )
        mgr, _, _ = _make_manager(seed=[c])
        revived = mgr.revive(c)
        reinforced = mgr.reinforce(revived)
        assert reinforced.lifecycle_state == "reinforced"
        assert reinforced.activation_state.score == pytest.approx(0.7)
        assert reinforced.activation_state.active is True


# ---------------------------------------------------------------------------
# transition() — generic
# ---------------------------------------------------------------------------


class TestTransition:
    def test_transition_accepts_string_target(self) -> None:
        c = _make_concern(lifecycle=LifecycleState.ACTIVE)
        mgr, _, _ = _make_manager(seed=[c])
        out = mgr.transition(c, "frozen")
        assert out.lifecycle_state == "frozen"
        assert out.activation_state is not None
        assert out.activation_state.active is False

    def test_transition_to_merged_deactivates(self) -> None:
        c = _make_concern(
            lifecycle=LifecycleState.ACTIVE,
            activation=ActivationState(score=0.6, active=True),
        )
        mgr, _, _ = _make_manager(seed=[c])
        out = mgr.transition(c, LifecycleState.MERGED, reason="folded into c-other")
        assert out.lifecycle_state == "merged"
        assert out.activation_state.active is False

    def test_transition_to_archived_syncs_dcn(self) -> None:
        c = _make_concern(lifecycle=LifecycleState.ACTIVE)
        mgr, _, ds = _make_manager(seed=[c])
        mgr.transition(c, LifecycleState.ARCHIVED)
        node = ds.get_node(c.id)
        assert node is not None
        assert node.lifecycle_state == "archived"

    def test_transition_invalid_path_raises(self) -> None:
        c = _make_concern(lifecycle=LifecycleState.ACTIVE)
        mgr, _, _ = _make_manager(seed=[c])
        # active → revived is not in the matrix (revive is only from
        # ARCHIVED).
        with pytest.raises(InvalidLifecycleTransition):
            mgr.transition(c, LifecycleState.REVIVED)

    def test_transition_idempotent_archive_no_op(self) -> None:
        c = _make_concern(lifecycle=LifecycleState.ARCHIVED)
        mgr, cs, _ = _make_manager(seed=[c])
        before = cs.get(c.id)
        out = mgr.transition(c, LifecycleState.ARCHIVED, reason="redundant")
        # Same updated_at (no real write happened).
        assert out.updated_at == before.updated_at
        assert out.lifecycle_state == "archived"

    def test_transition_unknown_string_target_raises(self) -> None:
        c = _make_concern(lifecycle=LifecycleState.ACTIVE)
        mgr, _, _ = _make_manager(seed=[c])
        with pytest.raises(ValueError):
            mgr.transition(c, "hibernate-deluxe")  # not a real state

    def test_full_lifecycle_path(self) -> None:
        # Walk the full happy path: created → reinforced → weakened
        # → reinforced → archived → revived → reinforced. Pin that
        # the matrix supports the canonical sequence end-to-end and
        # the store ends up consistent.
        c = _make_concern()
        mgr, cs, ds = _make_manager(seed=[c])

        c1 = mgr.reinforce(c)
        assert c1.lifecycle_state == "reinforced"

        c2 = mgr.weaken(c1)
        assert c2.lifecycle_state == "weakened"

        c3 = mgr.reinforce(c2)
        assert c3.lifecycle_state == "reinforced"

        c4 = mgr.archive(c3, reason="superseded")
        assert c4.lifecycle_state == "archived"
        # DCN must be in sync after archive.
        assert ds.get_node(c.id).lifecycle_state == "archived"

        c5 = mgr.revive(c4)
        assert c5.lifecycle_state == "revived"

        c6 = mgr.reinforce(c5)
        assert c6.lifecycle_state == "reinforced"

        # Store reflects the final state.
        stored = cs.get(c.id)
        assert stored.lifecycle_state == "reinforced"


# ---------------------------------------------------------------------------
# Determinism / clock injection
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_clock_is_used_for_updated_at(self) -> None:
        c = _make_concern()
        custom = datetime(2030, 6, 15, 12, 0, 0, tzinfo=UTC)
        mgr, _, _ = _make_manager(seed=[c], now=custom)
        out = mgr.reinforce(c)
        assert out.updated_at == custom
        assert out.activation_state.last_activated_at == custom

    def test_clock_called_per_mutation(self) -> None:
        # Two reinforces should see two different timestamps if the
        # clock advances. Pin this so a refactor that caches now()
        # at construction time gets caught.
        c = _make_concern()
        cs = MemoryConcernStore()
        ds = MemoryDCNStore()
        cs.upsert(c)
        ds.add_node(c)
        clicks = iter(
            [
                datetime(2026, 1, 1, tzinfo=UTC),
                datetime(2026, 1, 2, tzinfo=UTC),
            ]
        )
        mgr = ConcernLifecycleManager(
            concern_store=cs,
            dcn_store=ds,
            now=lambda: next(clicks),
        )
        first = mgr.reinforce(c)
        second = mgr.reinforce(first)
        assert first.updated_at != second.updated_at

    def test_returned_snapshot_round_trips(self) -> None:
        # The Concern returned by the manager must be a fully valid
        # envelope (round-trips through pydantic). Catches a bug
        # where we forget to coerce / set a required field.
        c = _make_concern()
        mgr, _, _ = _make_manager(seed=[c])
        out = mgr.reinforce(c)
        roundtrip = Concern.model_validate(out.model_dump())
        assert roundtrip.id == out.id
        assert roundtrip.lifecycle_state == out.lifecycle_state
        assert roundtrip.activation_state.score == out.activation_state.score


# ---------------------------------------------------------------------------
# Integration with stores
# ---------------------------------------------------------------------------


class TestStoreIntegration:
    def test_uses_store_state_not_caller_snapshot(self) -> None:
        # If the caller passes a stale Concern (lifecycle=CREATED
        # locally) but the store has already moved on (REINFORCED),
        # the manager should mutate from the store's truth, not the
        # caller's stale view.
        c_stale = _make_concern(lifecycle=LifecycleState.CREATED)
        c_real = _make_concern(
            lifecycle=LifecycleState.WEAKENED,
            activation=ActivationState(score=0.3),
        )
        mgr, _, _ = _make_manager(seed=[c_real])
        out = mgr.reinforce(c_stale, delta=0.2)
        # 0.3 + 0.2 = 0.5 — proves we read from store (which had 0.3)
        # not from the caller (which has score=None).
        assert out.activation_state.score == pytest.approx(0.5)

    def test_archive_no_dcn_node_is_safe(self) -> None:
        # Some concerns live in the concern_store but never made it
        # into the DCN (e.g. a freshly-extracted candidate that the
        # builder hasn't promoted yet). Archive must not blow up.
        c = _make_concern(lifecycle=LifecycleState.ACTIVE)
        cs = MemoryConcernStore()
        ds = MemoryDCNStore()
        cs.upsert(c)
        # Note: NOT calling ds.add_node(c).
        mgr = ConcernLifecycleManager(
            concern_store=cs,
            dcn_store=ds,
            now=lambda: _FIXED_NOW,
        )
        out = mgr.archive(c)
        assert out.lifecycle_state == "archived"

    def test_empty_id_raises(self) -> None:
        # Defence-in-depth: pydantic already rejects empty ids on
        # construction. The manager treats Concern.id as the lookup
        # key, so loosening this constraint upstream would silently
        # break persistence — pin it.
        with pytest.raises(ValueError):
            _make_concern(cid="")


# ---------------------------------------------------------------------------
# Decay interaction
# ---------------------------------------------------------------------------


class TestDecay:
    def test_decay_preserved_unless_reinforced(self) -> None:
        # Weaken should leave decay alone; only reinforce zeroes it.
        c = _make_concern(activation=ActivationState(score=0.5, decay=0.25))
        mgr, _, _ = _make_manager(seed=[c])
        weaker = mgr.weaken(c)
        assert weaker.activation_state.decay == pytest.approx(0.25)
        stronger = mgr.reinforce(weaker)
        assert stronger.activation_state.decay == 0.0

    def test_revive_zeroes_decay(self) -> None:
        c = _make_concern(
            lifecycle=LifecycleState.ARCHIVED,
            activation=ActivationState(score=0.5, decay=0.9),
        )
        mgr, _, _ = _make_manager(seed=[c])
        out = mgr.revive(c)
        assert out.activation_state.decay == 0.0


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------


class TestMisc:
    def test_default_clock_uses_utc(self) -> None:
        # No ``now=`` injected — the manager falls back to UTC datetime.
        c = _make_concern()
        cs = MemoryConcernStore()
        ds = MemoryDCNStore()
        cs.upsert(c)
        ds.add_node(c)
        mgr = ConcernLifecycleManager(concern_store=cs, dcn_store=ds)
        before = datetime.now(UTC) - timedelta(seconds=1)
        out = mgr.reinforce(c)
        after = datetime.now(UTC) + timedelta(seconds=1)
        assert before <= out.updated_at <= after

    def test_module_exports_match_init(self) -> None:
        # Pin the public surface — these are the names hosts can
        # rely on across releases.
        from COAT_runtime_core.concern import (
            ConcernLifecycleManager as Exported,
        )
        from COAT_runtime_core.concern import (
            InvalidLifecycleTransition as ErrExported,
        )

        assert Exported is ConcernLifecycleManager
        assert ErrExported is InvalidLifecycleTransition
