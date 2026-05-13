"""Emit a joinpoint event from arbitrary host code."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from opencoat_runtime_protocol import JoinpointEvent

from .client import Client


class JoinpointEmitter:
    def __init__(self, *, client: Client, host: str = "custom") -> None:
        self._client = client
        self._host = host

    def emit(
        self,
        name: str,
        *,
        level: int = 1,
        agent_session_id: str | None = None,
        turn_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> JoinpointEvent:
        jp = JoinpointEvent(
            id=f"jp-{uuid4().hex[:12]}",
            level=level,
            name=name,
            host=self._host,
            agent_session_id=agent_session_id,
            turn_id=turn_id,
            ts=datetime.now(UTC),
            payload=payload,
        )
        # Wire-up to client.emit() lands in M1.
        return jp
