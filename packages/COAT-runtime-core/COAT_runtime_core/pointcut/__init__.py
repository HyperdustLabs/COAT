"""Pointcut subsystem — match concerns against joinpoints.

12 strategies are wired in (lifecycle / role / prompt_path / keyword / regex /
semantic / structure / token / claim / confidence / risk / history) and
combined by :class:`PointcutMatcher`.
"""

from . import strategies
from .compiler import CompiledPointcut, PointcutCompiler, match_block_is_executable
from .matcher import PointcutMatcher

__all__ = [
    "CompiledPointcut",
    "PointcutCompiler",
    "PointcutMatcher",
    "match_block_is_executable",
    "strategies",
]
