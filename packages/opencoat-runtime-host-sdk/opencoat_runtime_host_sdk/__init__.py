"""OpenCOAT Runtime host-side SDK."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _version

from .client import Client
from .decorators import joinpoint
from .injection_consumer import InjectionConsumer
from .joinpoint_emitter import JoinpointEmitter

try:
    __version__ = _version("opencoat-runtime-host-sdk")
except PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = ["Client", "InjectionConsumer", "JoinpointEmitter", "joinpoint"]
