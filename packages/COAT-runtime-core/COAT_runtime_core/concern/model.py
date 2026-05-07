"""Re-exports the wire-format Concern model from the protocol package.

The core never defines a parallel data model: there is exactly one Concern
shape (in :mod:`COAT_runtime_protocol.envelopes`) and we use it everywhere.
"""

from __future__ import annotations

from COAT_runtime_protocol import (
    Advice,
    Concern,
    ConcernKind,
    ConcernRelationType,
    LifecycleState,
    MetaConcern,
    Pointcut,
    WeavingPolicy,
)
from COAT_runtime_protocol.envelopes import (
    ActivationState,
    ConcernMetrics,
    ConcernRelation,
    ConcernScope,
    ConcernSource,
    GovernanceCapability,
)

__all__ = [
    "ActivationState",
    "Advice",
    "Concern",
    "ConcernKind",
    "ConcernMetrics",
    "ConcernRelation",
    "ConcernRelationType",
    "ConcernScope",
    "ConcernSource",
    "GovernanceCapability",
    "LifecycleState",
    "MetaConcern",
    "Pointcut",
    "WeavingPolicy",
]
