"""Internal type aliases used across the core.

Keeps signatures readable without leaking implementation choices.
The wire-format types live in ``opencoat_runtime_protocol``.
"""

from __future__ import annotations

from typing import Any, Literal, TypeAlias

#: Stable identifier for a Concern.
ConcernId: TypeAlias = str

#: Stable identifier for a JoinpointEvent instance.
JoinpointId: TypeAlias = str

#: Stable identifier for one logical agent turn.
TurnId: TypeAlias = str

#: Stable identifier for one agent session.
SessionId: TypeAlias = str

#: Generic JSON-ish dict payload.
JSON: TypeAlias = dict[str, Any]

#: Confidence / score in the closed [0, 1] interval.
UnitFloat: TypeAlias = float

#: Risk level used by pointcut and resolver.
RiskLevel: TypeAlias = Literal["low", "medium", "high", "critical"]
