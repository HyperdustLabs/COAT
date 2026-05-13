"""Tiny end-to-end example agent driven by an in-process OpenCOATRuntime.

Importable so the smoke test under ``tests/integration/`` can run a turn
without subprocessing. The CLI lives in :mod:`.main`.
"""

from .agent import SimpleChatAgent, TurnReport
from .concerns import seed_concerns

__all__ = ["SimpleChatAgent", "TurnReport", "seed_concerns"]
