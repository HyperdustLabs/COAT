"""Tests for :class:`PointcutCompiler` and :class:`CompiledPointcut`."""

from __future__ import annotations

import re

import pytest
from opencoat_runtime_core.errors import PointcutCompileError
from opencoat_runtime_core.pointcut import (
    CompiledPointcut,
    PointcutCompiler,
    match_block_is_executable,
)
from opencoat_runtime_protocol import (
    ContextPredicate,
    JoinpointSelector,
    Pointcut,
    PointcutMatch,
)


def test_compile_empty_pointcut() -> None:
    compiled = PointcutCompiler().compile(Pointcut())
    assert isinstance(compiled, CompiledPointcut)
    assert compiled.joinpoint_names == frozenset()
    assert compiled.joinpoint_selectors == ()
    assert compiled.regex is None
    assert compiled.has_match_block is False
    assert compiled.has_context_predicates is False


def test_compile_splits_string_names_and_selectors() -> None:
    pc = Pointcut(
        joinpoints=[
            "before_response",
            "after_response",
        ]
    )
    compiled = PointcutCompiler().compile(pc)
    assert compiled.joinpoint_names == {"before_response", "after_response"}


def test_compile_with_selector_objects() -> None:
    sel = JoinpointSelector(level="prompt_section", path="runtime_prompt.verification_rules")
    pc = Pointcut(joinpoints=[sel])
    compiled = PointcutCompiler().compile(pc)
    assert compiled.joinpoint_selectors == (sel,)
    assert compiled.joinpoint_names == frozenset()


def test_compile_precompiles_regex() -> None:
    pc = Pointcut(match=PointcutMatch(regex=r"refund\s+#\d+"))
    compiled = PointcutCompiler().compile(pc)
    assert isinstance(compiled.regex, re.Pattern)
    assert compiled.regex.pattern == r"refund\s+#\d+"
    assert compiled.has_match_block is True


def test_compile_lowercases_keyword_sets() -> None:
    pc = Pointcut(match=PointcutMatch(any_keywords=["Refund", "CANCEL"], all_keywords=["Order"]))
    compiled = PointcutCompiler().compile(pc)
    assert compiled.any_keywords_lower == ("refund", "cancel")
    assert compiled.all_keywords_lower == ("order",)


def test_compile_invalid_regex_raises() -> None:
    pc = Pointcut(match=PointcutMatch(regex="[unclosed"))
    with pytest.raises(PointcutCompileError):
        PointcutCompiler().compile(pc)


def test_empty_keyword_lists_are_not_an_executable_match_block() -> None:
    """Regression: Codex PR review — empty lists must not activate `has_match_block`.

    Previously ``any_keywords=[]`` was truthy for ``is not None`` but the compiler
    skipped keyword compilation, leaving zero strategies and a spurious 1.0 score.
    """
    pc = Pointcut(match=PointcutMatch(any_keywords=[], all_keywords=[]))
    compiled = PointcutCompiler().compile(pc)
    assert compiled.has_match_block is False
    assert compiled.any_keywords_lower is None
    assert compiled.all_keywords_lower is None


def test_match_block_is_executable_helper() -> None:
    assert not match_block_is_executable(PointcutMatch(any_keywords=[], all_keywords=[]))
    assert not match_block_is_executable(PointcutMatch(semantic_intent="   "))
    assert match_block_is_executable(PointcutMatch(any_keywords=["x"]))
    assert match_block_is_executable(PointcutMatch(regex=r"."))


def test_has_context_predicates() -> None:
    pc = Pointcut(context_predicates=[ContextPredicate(key="tier", op="==", value="gold")])
    compiled = PointcutCompiler().compile(pc)
    assert compiled.has_context_predicates is True
    assert compiled.has_match_block is False
