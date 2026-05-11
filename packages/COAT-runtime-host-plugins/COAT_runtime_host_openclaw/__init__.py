"""OpenClaw host adapter for the COAT Runtime (M5)."""

from .adapter import OpenClawAdapter
from .events import OpenClawEvent, OpenClawEventName
from .joinpoint_map import OPENCLAW_EVENT_MAP, lookup_joinpoint

__all__ = [
    "OPENCLAW_EVENT_MAP",
    "OpenClawAdapter",
    "OpenClawEvent",
    "OpenClawEventName",
    "lookup_joinpoint",
]
