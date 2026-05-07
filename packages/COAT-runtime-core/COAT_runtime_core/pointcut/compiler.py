"""Pointcut compiler — turn a :class:`Pointcut` into an executable matcher.

The compiler precomputes the work that would otherwise repeat on every
joinpoint match: regex compilation, keyword-set normalisation, and the
split between catalog-name joinpoints and full :class:`JoinpointSelector`
filters. The result is a frozen :class:`CompiledPointcut` that can be
cached per-concern and reused across turns.

Compile-time errors (e.g. invalid regex) raise
:class:`COAT_runtime_core.errors.PointcutCompileError`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from COAT_runtime_protocol import JoinpointSelector, Pointcut

from ..errors import PointcutCompileError


@dataclass(frozen=True)
class CompiledPointcut:
    """Cached / pre-validated form of a :class:`Pointcut`."""

    source: Pointcut
    joinpoint_names: frozenset[str] = frozenset()
    joinpoint_selectors: tuple[JoinpointSelector, ...] = ()
    regex: re.Pattern[str] | None = None
    any_keywords_lower: tuple[str, ...] | None = None
    all_keywords_lower: tuple[str, ...] | None = None
    has_match_block: bool = False
    has_context_predicates: bool = field(default=False)


class PointcutCompiler:
    """Stateless compiler. Pure function disguised as a class for symmetry
    with the rest of the runtime's plugin types."""

    def compile(self, pointcut: Pointcut) -> CompiledPointcut:
        names, selectors = _split_joinpoints(pointcut.joinpoints)
        compiled_regex: re.Pattern[str] | None = None
        any_lower: tuple[str, ...] | None = None
        all_lower: tuple[str, ...] | None = None
        match_block = pointcut.match
        if match_block is not None:
            if match_block.regex is not None:
                try:
                    compiled_regex = re.compile(match_block.regex)
                except re.error as exc:
                    raise PointcutCompileError(
                        f"invalid regex in pointcut: {match_block.regex!r}: {exc}"
                    ) from exc
            if match_block.any_keywords:
                any_lower = tuple(k.lower() for k in match_block.any_keywords)
            if match_block.all_keywords:
                all_lower = tuple(k.lower() for k in match_block.all_keywords)

        return CompiledPointcut(
            source=pointcut,
            joinpoint_names=frozenset(names),
            joinpoint_selectors=tuple(selectors),
            regex=compiled_regex,
            any_keywords_lower=any_lower,
            all_keywords_lower=all_lower,
            has_match_block=_has_match_block(pointcut),
            has_context_predicates=bool(pointcut.context_predicates),
        )


def _split_joinpoints(
    joinpoints: list[str] | list[JoinpointSelector],
) -> tuple[list[str], list[JoinpointSelector]]:
    names: list[str] = []
    selectors: list[JoinpointSelector] = []
    for jp in joinpoints:
        if isinstance(jp, JoinpointSelector):
            selectors.append(jp)
        elif isinstance(jp, str):
            names.append(jp)
        else:
            raise PointcutCompileError(
                f"joinpoints must be str or JoinpointSelector, got {type(jp).__name__}"
            )
    return names, selectors


def _has_match_block(pointcut: Pointcut) -> bool:
    block = pointcut.match
    if block is None:
        return False
    return any(
        getattr(block, attr) is not None
        for attr in (
            "any_keywords",
            "all_keywords",
            "regex",
            "semantic_intent",
            "structure",
            "confidence",
            "risk",
            "history",
            "claim",
        )
    )


__all__ = ["CompiledPointcut", "PointcutCompiler"]
