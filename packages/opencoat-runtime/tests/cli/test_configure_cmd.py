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


# ---------------------------------------------------------------------------
# configure daemon
# ---------------------------------------------------------------------------


def _daemon_ns(**kwargs: object) -> Namespace:
    defaults: dict[str, object] = {
        "yaml": Path("/dev/null"),
        "concern_db": Path("/dev/null/concerns.sqlite"),
        "dcn_db": Path("/dev/null/dcn.sqlite"),
        "http_host": "127.0.0.1",
        "http_port": 7878,
        "http_path": "/rpc",
        "pid_file": Path("/dev/null/opencoat.pid"),
    }
    defaults.update(kwargs)
    return Namespace(**defaults)


def test_configure_daemon_writes_sqlite_storage(tmp_path: Path) -> None:
    y = tmp_path / "daemon.yaml"
    cdb = tmp_path / "store" / "concerns.sqlite"
    ddb = tmp_path / "store" / "dcn.sqlite"
    args = _daemon_ns(yaml=y, concern_db=cdb, dcn_db=ddb, pid_file=tmp_path / "opencoat.pid")
    assert configure_cmd._configure_daemon(args) == 0

    data = yaml.safe_load(y.read_text(encoding="utf-8"))
    assert data["storage"]["concern_store"] == {"kind": "sqlite", "path": str(cdb)}
    assert data["storage"]["dcn_store"] == {"kind": "sqlite", "path": str(ddb)}
    assert data["ipc"]["http"] == {
        "enabled": True,
        "host": "127.0.0.1",
        "port": 7878,
        "path": "/rpc",
    }
    # Parent dir for the sqlite files exists after configure runs.
    assert cdb.parent.is_dir()


def test_configure_daemon_preserves_existing_llm_block(tmp_path: Path) -> None:
    y = tmp_path / "daemon.yaml"
    y.write_text(
        "llm:\n  provider: openai\n  model: gpt-4o-mini\n  timeout_seconds: 30.0\n",
        encoding="utf-8",
    )
    args = _daemon_ns(
        yaml=y,
        concern_db=tmp_path / "c.sqlite",
        dcn_db=tmp_path / "d.sqlite",
        pid_file=tmp_path / "opencoat.pid",
    )
    assert configure_cmd._configure_daemon(args) == 0

    data = yaml.safe_load(y.read_text(encoding="utf-8"))
    assert data["llm"]["provider"] == "openai"
    assert data["llm"]["model"] == "gpt-4o-mini"
    assert data["storage"]["concern_store"]["kind"] == "sqlite"


def test_configure_daemon_then_llm_round_trip(tmp_path: Path) -> None:
    """Either-order: configure daemon → configure llm leaves both blocks intact."""
    y = tmp_path / "daemon.yaml"
    daemon_args = _daemon_ns(
        yaml=y,
        concern_db=tmp_path / "c.sqlite",
        dcn_db=tmp_path / "d.sqlite",
        pid_file=tmp_path / "opencoat.pid",
    )
    assert configure_cmd._configure_daemon(daemon_args) == 0

    llm_args = _ns(yaml=y, env=tmp_path / "e.env", mode="env-file", provider="openai")
    assert configure_cmd._configure_llm(llm_args) == 0

    data = yaml.safe_load(y.read_text(encoding="utf-8"))
    assert data["storage"]["concern_store"]["kind"] == "sqlite"
    assert data["llm"]["provider"] == "openai"
    assert data["ipc"]["http"]["port"] == 7878
