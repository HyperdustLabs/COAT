"""Hand-authored concerns for the long-running-daemon demo (M4 PR-23).

Same three rules as :mod:`examples.03_persistent_agent_demo.concerns` so
readers can compare M3 (in-proc + sqlite) vs M4 (daemon + HTTP JSON-RPC)
without learning new domain vocabulary. We keep a local copy rather
than importing the M3 module to avoid one example pulling another out
of disk shape just because of an ``__init__`` side effect.
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
            params={"regex": r"\[\d+\]|https?://", "case_sensitive": False},
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
    """Return the canonical demo concerns (same order as the M3 example)."""
    return [_be_concise(), _cite_sources(), _no_pii()]


__all__ = ["seed_concerns"]
