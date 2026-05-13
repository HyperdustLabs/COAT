"""Hand-authored concerns for the persistent-agent demo (M3 PR-16).

Reuses the same three-rule set as :mod:`examples.01_simple_chat_agent.concerns`
so readers can compare M1 (in-memory) vs M3 (sqlite + JSONL) without
learning new domain vocabulary.
"""

from __future__ import annotations

from opencoat_runtime_protocol import (
    Advice,
    AdviceType,
    Concern,
    Pointcut,
    WeavingLevel,
    WeavingOperation,
    WeavingPolicy,
)
from opencoat_runtime_protocol.envelopes import PointcutMatch


def _be_concise() -> Concern:
    return Concern(
        id="c-concise",
        name="Be concise",
        description="Keep replies short and direct; aim for ≤ 3 sentences.",
        pointcut=Pointcut(match=PointcutMatch(any_keywords=["?", "explain", "tell"])),
        advice=Advice(
            type=AdviceType.RESPONSE_REQUIREMENT,
            content="Reply in at most three sentences. No filler.",
        ),
        weaving_policy=WeavingPolicy(
            mode=WeavingOperation.INSERT,
            level=WeavingLevel.OUTPUT_LEVEL,
            target="runtime_prompt.output_format",
            priority=0.7,
        ),
    )


def _cite_sources() -> Concern:
    return Concern(
        id="c-cite",
        name="Cite sources for factual claims",
        description="Every answer that contains a factual claim must include a source.",
        pointcut=Pointcut(
            match=PointcutMatch(
                any_keywords=["who", "what", "when", "where", "why", "how"],
            )
        ),
        advice=Advice(
            type=AdviceType.VERIFICATION_RULE,
            content="The reply MUST contain at least one source URL or citation marker.",
            params={
                "regex": r"\[\d+\]|https?://",
                "case_sensitive": False,
            },
        ),
        weaving_policy=WeavingPolicy(
            mode=WeavingOperation.VERIFY,
            level=WeavingLevel.VERIFICATION_LEVEL,
            target="runtime_prompt.verification_rules",
            priority=0.9,
        ),
    )


def _no_pii() -> Concern:
    return Concern(
        id="c-no-pii",
        name="Never echo PII",
        description="Email addresses, phone numbers and SSNs must never appear in replies.",
        pointcut=Pointcut(
            match=PointcutMatch(
                any_keywords=["email", "phone", "ssn", "address"],
            )
        ),
        advice=Advice(
            type=AdviceType.TOOL_GUARD,
            content=(
                "If the answer would echo an email, phone number or SSN, redact it "
                "with [REDACTED] before responding."
            ),
        ),
        weaving_policy=WeavingPolicy(
            mode=WeavingOperation.BLOCK,
            level=WeavingLevel.OUTPUT_LEVEL,
            target="response.text",
            priority=1.0,
        ),
    )


def seed_concerns() -> list[Concern]:
    """Return the canonical demo concerns (same order as the M1 example)."""
    return [_be_concise(), _cite_sources(), _no_pii()]


__all__ = ["seed_concerns"]
