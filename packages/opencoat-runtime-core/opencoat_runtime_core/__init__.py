"""OpenCOAT Runtime core (L2 pure logic).

Public surface kept intentionally small. Heavy components live behind the
:class:`OpenCOATRuntime` facade and the ports under :mod:`opencoat_runtime_core.ports`.
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _version

from .config import RuntimeBudgets, RuntimeConfig
from .errors import (
    ConcernExtractionError,
    LLMTimeout,
    OpenCOATRuntimeError,
    PointcutCompileError,
    StoreUnavailable,
    WeavingBudgetExceeded,
)
from .runtime import OpenCOATRuntime

try:
    __version__ = _version("opencoat-runtime-core")
except PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "ConcernExtractionError",
    "LLMTimeout",
    "OpenCOATRuntime",
    "OpenCOATRuntimeError",
    "PointcutCompileError",
    "RuntimeBudgets",
    "RuntimeConfig",
    "StoreUnavailable",
    "WeavingBudgetExceeded",
]
