"""Concern Resolver — handle conflicts, duplicates, suppressions, escalations."""

from .conflict import ConflictResolver
from .dedupe import Dedupe
from .escalation import EscalationManager
from .resolver import ConcernResolver

__all__ = ["ConcernResolver", "ConflictResolver", "Dedupe", "EscalationManager"]
