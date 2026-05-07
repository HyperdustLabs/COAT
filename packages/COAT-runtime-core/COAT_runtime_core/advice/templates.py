"""Default advice templates, one per advice type.

Real templates land in M2; for M0 we only register the type → empty-template
mapping so downstream code can iterate over ``ADVICE_TEMPLATES``.
"""

from __future__ import annotations

from dataclasses import dataclass

from COAT_runtime_protocol import AdviceType


@dataclass(frozen=True)
class AdviceTemplate:
    type: AdviceType
    template: str
    description: str = ""


ADVICE_TEMPLATES: dict[AdviceType, AdviceTemplate] = {
    t: AdviceTemplate(type=t, template="", description="") for t in AdviceType
}
