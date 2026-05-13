"""Per-strategy pointcut matchers.

Every strategy is independently testable and self-contained. They share a
trivial protocol: ``apply(payload, context) -> MatchResult``.

12 strategies, one per file (v0.1 §13.2):

* :mod:`.lifecycle`     — match agent lifecycle stage
* :mod:`.role`          — match message role
* :mod:`.prompt_path`   — match prompt-section path (``runtime_prompt.…``)
* :mod:`.keyword`       — any/all keyword sets
* :mod:`.regex`         — regex match against text payloads
* :mod:`.semantic`      — semantic-intent match (LLM / embedding)
* :mod:`.structure`     — structured field comparison (operators)
* :mod:`.token`         — exact token / sub-token match
* :mod:`.claim`         — match against asserted claims
* :mod:`.confidence`    — operator + threshold over confidence score
* :mod:`.risk`          — operator + level over risk
* :mod:`.history`       — predicate over activation history
"""

from . import (
    claim,
    confidence,
    history,
    keyword,
    lifecycle,
    prompt_path,
    regex,
    risk,
    role,
    semantic,
    structure,
    token,
)

__all__ = [
    "claim",
    "confidence",
    "history",
    "keyword",
    "lifecycle",
    "prompt_path",
    "regex",
    "risk",
    "role",
    "semantic",
    "structure",
    "token",
]
