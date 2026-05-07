"""COAT Runtime core (L2 pure logic).

Public surface kept intentionally small. Heavy components live behind the
:class:`COATRuntime` facade and the ports under :mod:`COAT_runtime_core.ports`.
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _version

from .config import RuntimeBudgets, RuntimeConfig
from .errors import (
    COATRuntimeError,
    ConcernExtractionError,
    LLMTimeout,
    PointcutCompileError,
    StoreUnavailable,
    WeavingBudgetExceeded,
)
from .runtime import COATRuntime

try:
    __version__ = _version("COAT-runtime-core")
except PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "COATRuntime",
    "COATRuntimeError",
    "ConcernExtractionError",
    "LLMTimeout",
    "PointcutCompileError",
    "RuntimeBudgets",
    "RuntimeConfig",
    "StoreUnavailable",
    "WeavingBudgetExceeded",
]
