"""Message-role pointcut strategy."""

from __future__ import annotations

from ._base import JSON, NO_MATCH, JoinpointEvent, MatchResult, make_match


def apply(
    jp: JoinpointEvent, expected_roles: list[str], context: JSON | None = None
) -> MatchResult:
    """Match if the joinpoint's message role is in ``expected_roles``.

    Reads the role from ``payload.role`` (message payload kind). Returns
    ``NO_MATCH`` for any joinpoint whose payload doesn't carry a role.
    """
    if not expected_roles:
        return NO_MATCH
    payload = jp.payload or {}
    role = payload.get("role")
    if not isinstance(role, str):
        return NO_MATCH
    if role in expected_roles:
        return make_match(1.0, f"role:{role}")
    return NO_MATCH
