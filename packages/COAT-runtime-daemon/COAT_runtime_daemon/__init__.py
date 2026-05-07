"""COAT Runtime daemon — long-running service process."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _version

try:
    __version__ = _version("COAT-runtime-daemon")
except PackageNotFoundError:
    __version__ = "0.0.0"
