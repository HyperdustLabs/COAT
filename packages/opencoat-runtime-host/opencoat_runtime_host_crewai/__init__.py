"""CrewAI host adapter."""

from .adapter import CrewAIAdapter
from .joinpoint_map import CREWAI_EVENT_MAP

__all__ = ["CREWAI_EVENT_MAP", "CrewAIAdapter"]
