"""Tests for ``merge_user_llm_env_file`` (daemon startup env merge)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from opencoat_runtime_daemon.config.loader import merge_user_llm_env_file


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def test_merge_fills_missing_keys(fake_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_file = fake_home / ".opencoat" / "opencoat.env"
    env_file.parent.mkdir(parents=True, exist_ok=True)
    env_file.write_text(
        '# comment\nOPENAI_API_KEY=sk-from-file\nEMPTY=\n',
        encoding="utf-8",
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    merge_user_llm_env_file()
    assert os.environ.get("OPENAI_API_KEY") == "sk-from-file"


def test_merge_setdefault_does_not_override_shell(
    fake_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = fake_home / ".opencoat" / "opencoat.env"
    env_file.parent.mkdir(parents=True, exist_ok=True)
    env_file.write_text("OPENAI_API_KEY=sk-from-file\n", encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-from-shell")
    merge_user_llm_env_file()
    assert os.environ.get("OPENAI_API_KEY") == "sk-from-shell"


def test_merge_missing_file_is_noop(fake_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    merge_user_llm_env_file()
    assert os.environ.get("OPENAI_API_KEY") is None
