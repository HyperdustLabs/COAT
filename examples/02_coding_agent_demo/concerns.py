"""Hand-authored coding-agent concerns + matching governance doc.

The demo gives the host two equivalent on-ramps for the same
behaviour:

1. ``seed_concerns()`` — five hand-authored :class:`Concern`
   envelopes that pin every advice type the runtime supports
   (``response_requirement``, ``verification_rule``, ``tool_guard``,
   ``reasoning_guidance``).  CI uses these because they're
   deterministic and don't need a real LLM.
2. ``GOVERNANCE_DOC`` — the same five rules expressed as a short
   natural-language policy.  When the host is configured with a
   real LLM (M2 PR-7..PR-9), running
   :class:`ConcernExtractor.extract_from_governance_doc` against
   this string lands a roughly-equivalent set of Concerns.  The
   point isn't byte-for-byte equality; it's that the runtime can
   bootstrap from prose without changing any agent code.

The hand-authored set is the contract the integration tests assert
against; the governance doc is the developer-facing demo path.
"""

from __future__ import annotations

from COAT_runtime_protocol import (
    Advice,
    AdviceType,
    Concern,
    Pointcut,
    WeavingLevel,
    WeavingOperation,
    WeavingPolicy,
)
from COAT_runtime_protocol.envelopes import PointcutMatch

# ---------------------------------------------------------------------------
# Hand-authored Concerns
# ---------------------------------------------------------------------------


def _no_eval() -> Concern:
    return Concern(
        id="c-no-eval",
        name="Never emit eval() or exec()",
        description=(
            "Generated Python code must never call ``eval`` or ``exec`` on "
            "host-provided strings; suggest ``ast.literal_eval`` for parsing."
        ),
        pointcut=Pointcut(
            match=PointcutMatch(
                any_keywords=["eval", "exec", "dynamic", "metaprogram"],
            )
        ),
        advice=Advice(
            type=AdviceType.TOOL_GUARD,
            content=(
                "Do not include eval() or exec() in any code block. If the "
                "user asks for dynamic evaluation, recommend ast.literal_eval "
                "or an explicit parser instead."
            ),
        ),
        weaving_policy=WeavingPolicy(
            mode=WeavingOperation.BLOCK,
            level=WeavingLevel.OUTPUT_LEVEL,
            target="response.code_blocks",
            priority=1.0,
        ),
    )


def _type_hints() -> Concern:
    return Concern(
        id="c-type-hints",
        name="Public functions need type hints",
        description=(
            "Any Python function example shown to the user as a copy-paste "
            "must have parameter and return type annotations."
        ),
        pointcut=Pointcut(
            match=PointcutMatch(
                any_keywords=["def ", "function", "method", "implement", "write a"],
            )
        ),
        advice=Advice(
            type=AdviceType.RESPONSE_REQUIREMENT,
            content=(
                "Every Python function in the answer must include parameter "
                "type hints and a return-type annotation."
            ),
        ),
        weaving_policy=WeavingPolicy(
            mode=WeavingOperation.INSERT,
            level=WeavingLevel.OUTPUT_LEVEL,
            target="response.code_style",
            priority=0.7,
        ),
    )


def _cite_docs() -> Concern:
    return Concern(
        id="c-cite-docs",
        name="Cite the language reference",
        description=(
            "Answers about Python syntax / stdlib semantics must cite a doc "
            "URL so the user can verify the claim."
        ),
        pointcut=Pointcut(
            match=PointcutMatch(
                any_keywords=["how do i", "syntax", "what does", "stdlib", "module"],
            )
        ),
        advice=Advice(
            type=AdviceType.VERIFICATION_RULE,
            content=(
                "The reply MUST contain at least one URL pointing to "
                "official Python or library documentation."
            ),
            params={
                # Match either an explicit URL or a markdown-style citation
                # marker — the smoke test exercises both shapes.
                "regex": r"https?://|\[\d+\]",
                "case_sensitive": False,
            },
        ),
        weaving_policy=WeavingPolicy(
            mode=WeavingOperation.VERIFY,
            level=WeavingLevel.VERIFICATION_LEVEL,
            target="response.citations",
            priority=0.9,
        ),
    )


def _no_malware() -> Concern:
    return Concern(
        id="c-no-malware",
        name="Refuse harmful-code requests",
        description=(
            "Refuse requests for malware, password / token harvesting, "
            "or unauthorized-access tooling, even when framed as fiction."
        ),
        pointcut=Pointcut(
            match=PointcutMatch(
                any_keywords=[
                    "malware",
                    "exploit",
                    "keylogger",
                    "ransomware",
                    "rootkit",
                    "steal",
                    "exfiltrate",
                ],
            )
        ),
        advice=Advice(
            type=AdviceType.TOOL_GUARD,
            content=(
                "Refuse to write code whose primary purpose is harming a "
                "third party or bypassing security. Explain the refusal "
                "briefly and suggest a defensive alternative if relevant."
            ),
        ),
        weaving_policy=WeavingPolicy(
            mode=WeavingOperation.BLOCK,
            level=WeavingLevel.OUTPUT_LEVEL,
            target="response.text",
            priority=1.0,
        ),
    )


def _prefer_stdlib() -> Concern:
    return Concern(
        id="c-prefer-stdlib",
        name="Prefer the standard library",
        description=(
            "When two solutions are roughly equivalent, prefer the Python "
            "standard library to a third-party dependency."
        ),
        pointcut=Pointcut(
            match=PointcutMatch(
                any_keywords=["library", "package", "pip", "dependency", "import"],
            )
        ),
        advice=Advice(
            type=AdviceType.REASONING_GUIDANCE,
            content=(
                "Default to the Python standard library. Only reach for a "
                "third-party package when the stdlib answer is materially "
                "worse, and call out the trade-off when you do."
            ),
        ),
        weaving_policy=WeavingPolicy(
            mode=WeavingOperation.INSERT,
            level=WeavingLevel.PROMPT_LEVEL,
            target="reasoning.preferences",
            priority=0.5,
        ),
    )


def seed_concerns() -> list[Concern]:
    """Return the canonical demo set in declaration order.

    The integration tests pin both the ids and the order; reorder
    only with matching test updates.
    """
    return [
        _no_eval(),
        _type_hints(),
        _cite_docs(),
        _no_malware(),
        _prefer_stdlib(),
    ]


# ---------------------------------------------------------------------------
# Governance doc — the same rules in natural language
# ---------------------------------------------------------------------------


GOVERNANCE_DOC: str = """\
Coding-Agent Operating Policy
=============================

The following rules are non-negotiable.  An agent that violates any
of them is malfunctioning and must be stopped.

1. Never include calls to ``eval()`` or ``exec()`` in generated
   Python code.  When a user asks for dynamic evaluation, suggest
   ``ast.literal_eval`` or an explicit parser instead.

2. Every Python function shown to the user as a copy-paste example
   must include parameter type hints and a return-type annotation.

3. Answers about Python syntax or standard-library semantics must
   cite at least one URL pointing to the official Python docs (or a
   library's own documentation) so the user can verify the claim.

4. Refuse to write code whose primary purpose is harming a third
   party — malware, keyloggers, password harvesters, or
   unauthorized-access tooling — even when framed as fiction.
   Explain the refusal briefly.

5. Default to the Python standard library when it is materially
   sufficient for the task.  Reach for a third-party package only
   when the stdlib answer is meaningfully worse, and call out the
   trade-off when you do.
"""


__all__ = ["GOVERNANCE_DOC", "seed_concerns"]
