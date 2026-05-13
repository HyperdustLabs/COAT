"""OpenClaw host adapter for the OpenCOAT Runtime (M5)."""

from .adapter import OpenClawAdapter
from .config import OpenClawAdapterConfig
from .events import OpenClawEvent, OpenClawEventName
from .hooks import InstalledHooks, OpenClawHost, RuntimeLike, install_hooks
from .injector import OpenClawInjector
from .joinpoint_map import OPENCLAW_EVENT_MAP, lookup_joinpoint
from .memory_bridge import OpenClawMemoryBridge, OpenClawMemoryEvent
from .span_extractor import OpenClawSpanExtractor
from .tool_guard import OpenClawToolGuard, ToolGuardOutcome

__all__ = [
    "OPENCLAW_EVENT_MAP",
    "InstalledHooks",
    "OpenClawAdapter",
    "OpenClawAdapterConfig",
    "OpenClawEvent",
    "OpenClawEventName",
    "OpenClawHost",
    "OpenClawInjector",
    "OpenClawMemoryBridge",
    "OpenClawMemoryEvent",
    "OpenClawSpanExtractor",
    "OpenClawToolGuard",
    "RuntimeLike",
    "ToolGuardOutcome",
    "install_hooks",
    "lookup_joinpoint",
]
