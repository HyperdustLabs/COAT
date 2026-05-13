"""Escalation manager — promote ``escalation_notice`` advices to host alerts.

A concern escalates when **both**:

* its ``advice.type`` is ``escalation_notice``, and
* the concern is being injected into the current vector (the resolver
  decides which of those firings actually go through, then asks the
  manager to mint payloads for them).

The emitted payload is a plain dict so the daemon can serialize it
without depending on an envelope type. Hosts that want a typed envelope
can wrap the result in their own model.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from opencoat_runtime_protocol import Advice, AdviceType, Concern


class EscalationManager:
    """Detect ``escalation_notice`` advices and mint host alerts."""

    def should_escalate(self, concern: Concern, advice: Advice | None) -> bool:
        if advice is None:
            return False
        return advice.type == AdviceType.ESCALATION_NOTICE

    def emit(self, concern: Concern, advice: Advice) -> dict[str, Any]:
        return {
            "type": "escalation_notice",
            "concern_id": concern.id,
            "concern_name": concern.name,
            "rationale": advice.rationale,
            "content": advice.content,
            "ts": datetime.now(UTC).isoformat(),
        }


__all__ = ["EscalationManager"]
