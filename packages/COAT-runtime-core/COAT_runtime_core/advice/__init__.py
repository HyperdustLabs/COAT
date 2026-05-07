"""Advice subsystem — generate :class:`Advice` from a Concern + context.

11 advice types live in :mod:`.types`. Default templates live in
:mod:`.templates`. The default :class:`AdvicePlugin` is :class:`AdviceGenerator`.
"""

from .generator import AdviceGenerator
from .templates import ADVICE_TEMPLATES, AdviceTemplate
from .types import ADVICE_TYPES

__all__ = ["ADVICE_TEMPLATES", "ADVICE_TYPES", "AdviceGenerator", "AdviceTemplate"]
