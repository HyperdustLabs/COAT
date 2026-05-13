"""Concern lifecycle modules — extractor, separator, builder, verifier, lifecycle, vector.

The data model itself comes from :mod:`opencoat_runtime_protocol.envelopes`; we
re-export it from :mod:`.model` as a convenience.
"""

from . import model
from .builder import ConcernBuilder
from .extractor import ConcernExtractor, ExtractionResult, Rejection
from .lifecycle import ConcernLifecycleManager, InvalidLifecycleTransition
from .separator import ConcernSeparator
from .vector import ConcernVectorBuilder
from .verifier import ConcernVerifier, VerificationResult

__all__ = [
    "ConcernBuilder",
    "ConcernExtractor",
    "ConcernLifecycleManager",
    "ConcernSeparator",
    "ConcernVectorBuilder",
    "ConcernVerifier",
    "ExtractionResult",
    "InvalidLifecycleTransition",
    "Rejection",
    "VerificationResult",
    "model",
]
