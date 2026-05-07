"""LLM / Embedder clients."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _version

from .stub_client import StubLLMClient

try:
    __version__ = _version("COAT-runtime-llm")
except PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = ["StubLLMClient"]
