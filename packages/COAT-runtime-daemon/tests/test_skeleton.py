"""M0 smoke tests — daemon skeleton + config load."""

from __future__ import annotations

import importlib

import pytest


@pytest.mark.parametrize(
    "modname",
    [
        "COAT_runtime_daemon",
        "COAT_runtime_daemon.daemon",
        "COAT_runtime_daemon.scheduler",
        "COAT_runtime_daemon.service",
        "COAT_runtime_daemon.supervisor",
        "COAT_runtime_daemon.health",
        "COAT_runtime_daemon.workers",
        "COAT_runtime_daemon.workers.extraction_worker",
        "COAT_runtime_daemon.workers.verification_worker",
        "COAT_runtime_daemon.workers.decay_worker",
        "COAT_runtime_daemon.workers.conflict_scanner",
        "COAT_runtime_daemon.workers.merge_archiver",
        "COAT_runtime_daemon.workers.meta_review_worker",
        "COAT_runtime_daemon.ipc",
        "COAT_runtime_daemon.ipc.inproc",
        "COAT_runtime_daemon.ipc.socket_server",
        "COAT_runtime_daemon.ipc.http_server",
        "COAT_runtime_daemon.ipc.jsonrpc_server",
        "COAT_runtime_daemon.ipc.grpc_server",
        "COAT_runtime_daemon.api",
        "COAT_runtime_daemon.api.joinpoint_api",
        "COAT_runtime_daemon.api.concern_api",
        "COAT_runtime_daemon.api.dcn_api",
        "COAT_runtime_daemon.api.injection_api",
        "COAT_runtime_daemon.api.admin_api",
        "COAT_runtime_daemon.config",
        "COAT_runtime_daemon.config.loader",
    ],
)
def test_module_imports(modname: str) -> None:
    importlib.import_module(modname)


def test_default_config_loads() -> None:
    from COAT_runtime_daemon.config import load_config

    cfg = load_config()
    assert cfg.runtime.schema_version == "0.2"
    assert cfg.storage.concern_store.kind == "memory"
    assert cfg.llm.provider == "stub"
    assert cfg.ipc.inproc.enabled is True


def test_check_config_cli_branch(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from COAT_runtime_daemon.__main__ import main

    rc = main(["--check-config"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "config OK" in out
