"""Ports — abstract interfaces every adapter must implement.

The core never depends on a concrete adapter: callers wire concrete
implementations (memory store, openai client, etc.) at startup.
"""

from .advice_plugin import AdvicePlugin
from .concern_store import ConcernStore
from .dcn_store import DCNStore
from .embedder import Embedder
from .host_adapter import HostAdapter
from .llm import LLMClient
from .matcher import MatcherPlugin
from .observer import Observer

__all__ = [
    "AdvicePlugin",
    "ConcernStore",
    "DCNStore",
    "Embedder",
    "HostAdapter",
    "LLMClient",
    "MatcherPlugin",
    "Observer",
]
