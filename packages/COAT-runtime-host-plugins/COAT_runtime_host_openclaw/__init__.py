"""OpenClaw host adapter for the COAT Runtime."""

from .adapter import OpenClawAdapter
from .joinpoint_map import OPENCLAW_EVENT_MAP

__all__ = ["OPENCLAW_EVENT_MAP", "OpenClawAdapter"]
