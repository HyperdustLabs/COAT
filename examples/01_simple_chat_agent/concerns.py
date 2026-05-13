"""Hand-authored concerns for the simple chat-agent example.

In M1 the :class:`ConcernExtractor` is still a stub, so this example
takes the pragmatic shortcut of declaring concerns directly. From M2
onwards the same concerns can be produced by the extractor from
governance docs / dialogue history; the runtime contract does not
change.

The three concerns below were chosen to exercise three different
slices of the runtime:

* a **response requirement** that lands as a non-verifying advice
  (purely steering),
* a **verification rule** with a regex check (so the verifier has a
  real rule to apply),
* a **tool / output guard** that demonstrates a richer pointcut
  (multiple keywords, target an output-level operation).

They are deliberately tiny — the point of the example is the *plumbing*,
not domain modelling.
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
                # Regex satisfied by either a markdown citation token like
                # "[1]" or an http(s) URL. Both are common in answers and
                # cheap to detect.
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
                # ``any_keywords`` is normalised to lowercase by the
                # compiler, so case here is irrelevant.
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
    """Return the canonical set of demo concerns in declaration order.

    Tests rely on this order for stable id assertions; do not reorder
    without updating the smoke test.
    """
    return [_be_concise(), _cite_sources(), _no_pii()]


__all__ = ["seed_concerns"]
