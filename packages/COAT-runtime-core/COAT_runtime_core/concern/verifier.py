"""Concern Verifier — v0.1 §20.11.

Checks the host's output against every active Concern's verification rules
and produces a per-turn satisfaction report.

A concern is considered for verification when it carries a
``verification_rule`` advice. Rule resolution order (M1):

1. ``advice.params['regex']`` — the rule passes when the regex matches
   the host output (case-insensitive by default; opt out with
   ``advice.params['case_sensitive'] = True``).
2. ``advice.params['must_contain']`` (string or list of strings) — every
   listed substring must appear in the host output.
3. ``advice.params['must_not_contain']`` (string or list) — none of the
   listed substrings may appear.
4. ``advice.params['use_llm'] = True`` *and* an :class:`LLMClient` is
   wired — the verifier asks the LLM for a yes/no judgement using the
   advice content as the criterion. The text reply is parsed
   conservatively (anything starting with ``yes`` / ``true`` / ``pass``
   counts as satisfied).
5. *Otherwise* — the result is ``satisfied=False`` with
   ``score=0.5`` and notes ``"no rule"``, signalling that the host
   should treat the concern as advisory only. This avoids silent
   false-positives when a rule was forgotten.

The verifier is sync, idempotent and free of side effects beyond the LLM
call. ``verify_turn`` skips concerns that are not in ``active`` so callers
can pass the full concern catalog without worrying about scope.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from COAT_runtime_protocol import Advice, AdviceType, Concern, ConcernVector

from ..ports import LLMClient


@dataclass(frozen=True)
class VerificationResult:
    concern_id: str
    satisfied: bool
    score: float = 0.0
    evidence: dict = field(default_factory=dict)
    notes: str = ""


_PASS_PREFIXES = ("yes", "true", "pass", "ok", "satisf")


class ConcernVerifier:
    def __init__(self, *, llm: LLMClient | None = None) -> None:
        self._llm = llm

    def verify_turn(
        self,
        *,
        active: ConcernVector,
        concerns: list[Concern],
        host_output: str,
        host_context: dict | None = None,
    ) -> list[VerificationResult]:
        active_ids = {a.concern_id for a in active.active_concerns}
        results: list[VerificationResult] = []
        for concern in concerns:
            if concern.id not in active_ids:
                continue
            results.append(
                self.verify_one(concern, host_output=host_output, host_context=host_context)
            )
        return results

    def verify_one(
        self,
        concern: Concern,
        *,
        host_output: str,
        host_context: dict | None = None,
    ) -> VerificationResult:
        advice = concern.advice
        if advice is None or AdviceType(advice.type) != AdviceType.VERIFICATION_RULE:
            return VerificationResult(
                concern_id=concern.id,
                satisfied=False,
                score=0.5,
                notes="no verification advice",
            )

        params = advice.params or {}
        if "regex" in params:
            return self._verify_regex(concern.id, host_output, params)
        if "must_contain" in params:
            return self._verify_must_contain(concern.id, host_output, params)
        if "must_not_contain" in params:
            return self._verify_must_not_contain(concern.id, host_output, params)
        if params.get("use_llm") and self._llm is not None:
            return self._verify_llm(concern.id, host_output, advice)
        return VerificationResult(
            concern_id=concern.id,
            satisfied=False,
            score=0.5,
            notes="no rule",
        )

    # ------------------------------------------------------------------
    # Rule implementations
    # ------------------------------------------------------------------

    @staticmethod
    def _verify_regex(concern_id: str, output: str, params: dict) -> VerificationResult:
        flags = 0 if params.get("case_sensitive") else re.IGNORECASE
        try:
            pattern = re.compile(params["regex"], flags)
        except re.error as exc:
            return VerificationResult(
                concern_id=concern_id,
                satisfied=False,
                score=0.0,
                notes=f"invalid regex: {exc}",
            )
        match = pattern.search(output)
        return VerificationResult(
            concern_id=concern_id,
            satisfied=bool(match),
            score=1.0 if match else 0.0,
            evidence={"matched": bool(match), "group": match.group(0) if match else None},
            notes="regex",
        )

    @staticmethod
    def _verify_must_contain(
        concern_id: str,
        output: str,
        params: dict,
    ) -> VerificationResult:
        needles = _as_list(params["must_contain"])
        haystack = output if params.get("case_sensitive") else output.lower()
        cmp = [(n, n if params.get("case_sensitive") else n.lower()) for n in needles]
        missing = [orig for orig, lo in cmp if lo not in haystack]
        return VerificationResult(
            concern_id=concern_id,
            satisfied=not missing,
            score=1.0 if not missing else max(0.0, 1.0 - len(missing) / max(len(cmp), 1)),
            evidence={"missing": missing},
            notes="must_contain",
        )

    @staticmethod
    def _verify_must_not_contain(
        concern_id: str,
        output: str,
        params: dict,
    ) -> VerificationResult:
        needles = _as_list(params["must_not_contain"])
        haystack = output if params.get("case_sensitive") else output.lower()
        cmp = [(n, n if params.get("case_sensitive") else n.lower()) for n in needles]
        present = [orig for orig, lo in cmp if lo in haystack]
        return VerificationResult(
            concern_id=concern_id,
            satisfied=not present,
            score=1.0 if not present else 0.0,
            evidence={"present": present},
            notes="must_not_contain",
        )

    def _verify_llm(self, concern_id: str, output: str, advice: Advice) -> VerificationResult:
        assert self._llm is not None  # type-narrowing for the LLM branch
        criterion = advice.content
        prompt = (
            f"Criterion: {criterion}\n\n"
            f"Output to judge:\n{output}\n\n"
            "Reply with 'yes' if the output satisfies the criterion, "
            "otherwise 'no'."
        )
        reply = self._llm.complete(prompt, max_tokens=4).strip().lower()
        satisfied = reply.startswith(_PASS_PREFIXES)
        return VerificationResult(
            concern_id=concern_id,
            satisfied=satisfied,
            score=1.0 if satisfied else 0.0,
            evidence={"llm_reply": reply},
            notes="llm",
        )


def _as_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


__all__ = ["ConcernVerifier", "VerificationResult"]
