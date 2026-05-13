"""OpenCOAT Runtime daemon — long-running service process."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _version

from .daemon import Daemon, DaemonAlreadyStartedError
from .runtime_builder import BuiltRuntime, build_runtime

try:
    __version__ = _version("opencoat-runtime")
except PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "BuiltRuntime",
    "Daemon",
    "DaemonAlreadyStartedError",
    "build_runtime",
]
