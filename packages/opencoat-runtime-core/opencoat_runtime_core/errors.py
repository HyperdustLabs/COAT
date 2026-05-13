"""Typed errors raised by the OpenCOAT Runtime core.

All runtime errors derive from :class:`OpenCOATRuntimeError`. The daemon maps
these to JSON-RPC error codes (see ``packages/opencoat-runtime-daemon``).
"""

from __future__ import annotations


class OpenCOATRuntimeError(Exception):
    """Base class for every error emitted by the core."""


# --- Concern lifecycle -----------------------------------------------------


class ConcernExtractionError(OpenCOATRuntimeError):
    """Raised when the extractor cannot produce a usable Concern from a source."""


class ConcernSeparationError(OpenCOATRuntimeError):
    """Raised when the separator cannot split / merge a Concern."""


class ConcernVerificationError(OpenCOATRuntimeError):
    """Raised when the verifier itself fails (not when verification = unsatisfied)."""


# --- AOP machinery ---------------------------------------------------------


class PointcutCompileError(OpenCOATRuntimeError):
    """Raised when a pointcut cannot be compiled into an executable matcher."""


class WeavingBudgetExceeded(OpenCOATRuntimeError):
    """Raised when weaving would exceed the configured token / count budget."""


class WeavingTargetUnknown(OpenCOATRuntimeError):
    """Raised when an advice targets a path the host did not register."""


# --- Adapters --------------------------------------------------------------


class StoreUnavailable(OpenCOATRuntimeError):
    """Concern / DCN store could not be reached."""


class LLMTimeout(OpenCOATRuntimeError):
    """LLM client exceeded its configured timeout."""


class HostAdapterError(OpenCOATRuntimeError):
    """The host adapter rejected an injection or a joinpoint event."""
