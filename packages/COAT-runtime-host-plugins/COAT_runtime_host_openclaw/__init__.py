"""OpenClaw host adapter for the COAT Runtime (M5)."""

from .adapter import OpenClawAdapter
from .config import OpenClawAdapterConfig
from .events import OpenClawEvent, OpenClawEventName
from .injector import OpenClawInjector
from .joinpoint_map import OPENCLAW_EVENT_MAP, lookup_joinpoint
from .span_extractor import OpenClawSpanExtractor

__all__ = [
    "OPENCLAW_EVENT_MAP",
    "OpenClawAdapter",
    "OpenClawAdapterConfig",
    "OpenClawEvent",
    "OpenClawEventName",
    "OpenClawInjector",
    "OpenClawSpanExtractor",
    "lookup_joinpoint",
]
