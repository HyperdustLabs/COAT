"""Tests for ``COATr inspect joinpoints | pointcuts`` (M4 PR-22)."""

from __future__ import annotations

import argparse

import pytest
from opencoat_runtime_cli.commands import inspect_cmd


def _ns(what: str) -> argparse.Namespace:
    return argparse.Namespace(what=what)


def test_inspect_joinpoints_lists_well_known_names(capsys: pytest.CaptureFixture[str]) -> None:
    rc = inspect_cmd._handle(_ns("joinpoints"))
    out = capsys.readouterr().out
    assert rc == 0
    # spot-check one from each v0.1 §12 family
    assert "runtime_start" in out
    assert "before_reasoning" in out
    assert "assistant_message" in out
    assert "system_prompt.role_definition" in out
    # level labels are rendered first column
    assert "runtime" in out
    assert "lifecycle" in out


def test_inspect_pointcuts_lists_twelve_strategies(capsys: pytest.CaptureFixture[str]) -> None:
    rc = inspect_cmd._handle(_ns("pointcuts"))
    out = capsys.readouterr().out
    assert rc == 0
    # v0.1 §13.2 names the 12 strategies; assert each appears.
    for name in (
        "lifecycle",
        "role",
        "prompt_path",
        "keyword",
        "regex",
        "semantic",
        "structure",
        "token",
        "claim",
        "confidence",
        "risk",
        "history",
    ):
        assert name in out
    # at least one description from the docstring should be carried through
    assert "operator + threshold over confidence score" in out
