"""Concern Lifecycle Manager — v0.1 §20.12.

States: created → active → reinforced ↔ weakened → merged | frozen | archived
        → deleted | revived.
"""

from __future__ import annotations

from COAT_runtime_protocol import Concern, LifecycleState

from ..ports import ConcernStore, DCNStore


class ConcernLifecycleManager:
    def __init__(self, *, concern_store: ConcernStore, dcn_store: DCNStore) -> None:
        self._concern_store = concern_store
        self._dcn_store = dcn_store

    def transition(self, concern: Concern, target: LifecycleState, *, reason: str = "") -> Concern:
        raise NotImplementedError

    def reinforce(self, concern: Concern, delta: float = 0.1) -> Concern:
        raise NotImplementedError

    def weaken(self, concern: Concern, delta: float = 0.1) -> Concern:
        raise NotImplementedError

    def archive(self, concern: Concern, *, reason: str = "") -> Concern:
        raise NotImplementedError

    def revive(self, concern: Concern) -> Concern:
        raise NotImplementedError
