"""Typed errors raised by the COAT Runtime core.

All runtime errors derive from :class:`COATRuntimeError`. The daemon maps
these to JSON-RPC error codes (see ``packages/COAT-runtime-daemon``).
"""

from __future__ import annotations


class COATRuntimeError(Exception):
    """Base class for every error emitted by the core."""


# --- Concern lifecycle -----------------------------------------------------


class ConcernExtractionError(COATRuntimeError):
    """Raised when the extractor cannot produce a usable Concern from a source."""


class ConcernSeparationError(COATRuntimeError):
    """Raised when the separator cannot split / merge a Concern."""


class ConcernVerificationError(COATRuntimeError):
    """Raised when the verifier itself fails (not when verification = unsatisfied)."""


# --- AOP machinery ---------------------------------------------------------


class PointcutCompileError(COATRuntimeError):
    """Raised when a pointcut cannot be compiled into an executable matcher."""


class WeavingBudgetExceeded(COATRuntimeError):
    """Raised when weaving would exceed the configured token / count budget."""


class WeavingTargetUnknown(COATRuntimeError):
    """Raised when an advice targets a path the host did not register."""


# --- Adapters --------------------------------------------------------------


class StoreUnavailable(COATRuntimeError):
    """Concern / DCN store could not be reached."""


class LLMTimeout(COATRuntimeError):
    """LLM client exceeded its configured timeout."""


class HostAdapterError(COATRuntimeError):
    """The host adapter rejected an injection or a joinpoint event."""
