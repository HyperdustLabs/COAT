"""LLM / Embedder clients.

Real providers (OpenAI, Anthropic, Azure, Ollama) live in this package.
Each is loaded lazily so importing :mod:`COAT_runtime_llm` does not pull
in the upstream SDK — that only happens when a host actually constructs
the matching client. Users install the provider they want via the
matching optional extra::

    pip install COAT-runtime-llm[openai]
    pip install COAT-runtime-llm[anthropic]

The deterministic in-process stub used by tests + the M1 example lives
in :mod:`COAT_runtime_core.llm` and is re-exported below for the
``from COAT_runtime_llm import StubLLMClient`` import path that
predates the split.
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _version
from typing import TYPE_CHECKING, Any

from .stub_client import StubLLMClient

try:
    __version__ = _version("COAT-runtime-llm")
except PackageNotFoundError:
    __version__ = "0.0.0"


# Lazy attribute access keeps the SDK import out of module load time.
# ``from COAT_runtime_llm import OpenAILLMClient`` works only when the
# matching extra is installed; otherwise the import inside the adapter
# raises :class:`OpenAIClientError` with a fix-it-yourself message.
def __getattr__(name: str) -> Any:
    if name in {"OpenAILLMClient", "OpenAIClientError"}:
        from .openai_client import OpenAIClientError, OpenAILLMClient

        return {"OpenAILLMClient": OpenAILLMClient, "OpenAIClientError": OpenAIClientError}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


if TYPE_CHECKING:  # pragma: no cover — re-exported for static analysis only
    from .openai_client import OpenAIClientError, OpenAILLMClient

__all__ = ["OpenAIClientError", "OpenAILLMClient", "StubLLMClient"]
