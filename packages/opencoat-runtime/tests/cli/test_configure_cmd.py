"""Tests for ``opencoat configure llm``."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import yaml
from opencoat_runtime_cli.commands import configure_cmd


def _ns(**kwargs: object) -> Namespace:
    defaults: dict[str, object] = {
        "yaml": Path("/dev/null"),
        "env": Path("/dev/null"),
        "mode": "env-file",
        "non_interactive": True,
        "provider": "openai",
        "timeout_seconds": 25.0,
        "model": "gpt-4o-mini",
        "openai_api_key": "sk-test-openai",
        "openai_model_env": None,
        "anthropic_api_key": None,
        "anthropic_model_env": None,
        "azure_api_key": None,
        "azure_endpoint": None,
        "azure_deployment": None,
        "openai_base_url": None,
        "anthropic_base_url": None,
    }
    defaults.update(kwargs)
    return Namespace(**defaults)


def test_non_interactive_openai_env_file_writes_yaml_and_env(tmp_path: Path) -> None:
    y = tmp_path / "daemon.yaml"
    e = tmp_path / "opencoat.env"
    args = _ns(yaml=y, env=e, mode="env-file", provider="openai")
    assert configure_cmd._configure_llm(args) == 0
    data = yaml.safe_load(y.read_text(encoding="utf-8"))
    assert data["llm"]["provider"] == "openai"
    assert data["llm"]["model"] == "gpt-4o-mini"
    assert data["llm"]["timeout_seconds"] == 25.0
    text = e.read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=sk-test-openai" in text
    assert "sk-test-openai" not in y.read_text()


def test_non_interactive_inline_openai_embeds_key_in_yaml(tmp_path: Path) -> None:
    y = tmp_path / "d.yaml"
    e = tmp_path / "e.env"
    args = _ns(
        yaml=y,
        env=e,
        mode="inline",
        openai_api_key="sk-inline",
        openai_base_url="https://example.com/v1",
    )
    assert configure_cmd._configure_llm(args) == 0
    data = yaml.safe_load(y.read_text(encoding="utf-8"))
    assert data["llm"]["api_key"] == "sk-inline"
    assert data["llm"]["base_url"] == "https://example.com/v1"
    assert not e.exists()


def test_yaml_merge_preserves_other_top_level_keys(tmp_path: Path) -> None:
    y = tmp_path / "daemon.yaml"
    y.write_text(
        "ipc:\n  http:\n    enabled: true\n    host: 127.0.0.1\n    port: 7878\n",
        encoding="utf-8",
    )
    args = _ns(
        yaml=y,
        env=tmp_path / "e.env",
        mode="inline",
        provider="stub",
        model=None,
        openai_api_key=None,
        timeout_seconds=30.0,
    )
    assert configure_cmd._configure_llm(args) == 0
    data = yaml.safe_load(y.read_text(encoding="utf-8"))
    assert data["ipc"]["http"]["port"] == 7878
    assert data["llm"]["provider"] == "stub"


def test_non_interactive_inline_auto_rejected(tmp_path: Path) -> None:
    from argparse import Namespace

    import pytest

    args = Namespace(
        yaml=tmp_path / "d.yaml",
        env=tmp_path / "e.env",
        mode="inline",
        non_interactive=True,
        provider="auto",
        timeout_seconds=30.0,
        model=None,
        openai_api_key="sk-x",
        openai_model_env=None,
        anthropic_api_key=None,
        anthropic_model_env=None,
        azure_api_key=None,
        azure_endpoint=None,
        azure_deployment=None,
        openai_base_url=None,
        anthropic_base_url=None,
    )
    with pytest.raises(SystemExit) as excinfo:
        configure_cmd._configure_llm(args)
    assert excinfo.value.code == 2
    p = tmp_path / "x.env"
    p.write_text("A=1\n# c\nB=two\n", encoding="utf-8")
    assert configure_cmd._parse_env_file(p) == {"A": "1", "B": "two"}
