"""Concern Verifier — v0.1 §20.11.

Checks the host's output against every active Concern's verification rules
and produces a per-turn satisfaction report.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from COAT_runtime_protocol import Concern, ConcernVector

from ..ports import LLMClient


@dataclass(frozen=True)
class VerificationResult:
    concern_id: str
    satisfied: bool
    score: float = 0.0
    evidence: dict = field(default_factory=dict)
    notes: str = ""


class ConcernVerifier:
    def __init__(self, *, llm: LLMClient) -> None:
        self._llm = llm

    def verify_turn(
        self,
        *,
        active: ConcernVector,
        concerns: list[Concern],
        host_output: str,
        host_context: dict | None = None,
    ) -> list[VerificationResult]:
        raise NotImplementedError

    def verify_one(
        self,
        concern: Concern,
        *,
        host_output: str,
        host_context: dict | None = None,
    ) -> VerificationResult:
        raise NotImplementedError
