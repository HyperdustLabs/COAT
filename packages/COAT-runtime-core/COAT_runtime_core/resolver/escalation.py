"""Escalation manager — promote ``escalation_notice`` advices to host alerts."""

from __future__ import annotations

from COAT_runtime_protocol import Advice, Concern


class EscalationManager:
    def should_escalate(self, concern: Concern, advice: Advice) -> bool:
        raise NotImplementedError

    def emit(self, concern: Concern, advice: Advice) -> dict:
        raise NotImplementedError
