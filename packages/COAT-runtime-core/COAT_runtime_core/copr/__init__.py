"""COPR — Concern-Oriented Prompt Representation (v0.1 §16).

Replaces flat prompt strings with a structured tree (Thought DOM) so
pointcuts can match at sub-message granularity.
"""

from .model import COPR, CoprMessage, CoprPromptSection, CoprSpan
from .parser import CoprParser
from .renderer import CoprRenderer
from .span_segmenter import SpanSegmenter
from .tokenizer import CoprTokenizer

__all__ = [
    "COPR",
    "CoprMessage",
    "CoprParser",
    "CoprPromptSection",
    "CoprRenderer",
    "CoprSpan",
    "CoprTokenizer",
    "SpanSegmenter",
]
