"""Coding-agent demo (M2).

A minimally-realistic coding-assistant host wired against
:class:`OpenCOATRuntime` with a real LLM provider when one is configured
in the environment, falling back to the deterministic stub for CI.

Importable so the smoke test under ``tests/integration/`` can run a
turn without subprocessing. The CLI lives in :mod:`.main`.
"""

from .agent import CodingAgent, TurnReport
from .concerns import GOVERNANCE_DOC, seed_concerns
from .llm import select_llm

__all__ = [
    "GOVERNANCE_DOC",
    "CodingAgent",
    "TurnReport",
    "seed_concerns",
    "select_llm",
]
