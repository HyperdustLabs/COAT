"""M0 smoke tests — daemon skeleton + config load."""

from __future__ import annotations

import importlib

import pytest


@pytest.mark.parametrize(
    "modname",
    [
        "opencoat_runtime_daemon",
        "opencoat_runtime_daemon.daemon",
        "opencoat_runtime_daemon.scheduler",
        "opencoat_runtime_daemon.service",
        "opencoat_runtime_daemon.supervisor",
        "opencoat_runtime_daemon.health",
        "opencoat_runtime_daemon.workers",
        "opencoat_runtime_daemon.workers.extraction_worker",
        "opencoat_runtime_daemon.workers.verification_worker",
        "opencoat_runtime_daemon.workers.decay_worker",
        "opencoat_runtime_daemon.workers.conflict_scanner",
        "opencoat_runtime_daemon.workers.merge_archiver",
        "opencoat_runtime_daemon.workers.meta_review_worker",
        "opencoat_runtime_daemon.ipc",
        "opencoat_runtime_daemon.ipc.inproc",
        "opencoat_runtime_daemon.ipc.socket_server",
        "opencoat_runtime_daemon.ipc.http_server",
        "opencoat_runtime_daemon.ipc.jsonrpc_server",
        "opencoat_runtime_daemon.ipc.jsonrpc_dispatch",
        "opencoat_runtime_daemon.ipc.grpc_server",
        "opencoat_runtime_daemon.api",
        "opencoat_runtime_daemon.api.joinpoint_api",
        "opencoat_runtime_daemon.api.concern_api",
        "opencoat_runtime_daemon.api.dcn_api",
        "opencoat_runtime_daemon.api.injection_api",
        "opencoat_runtime_daemon.api.admin_api",
        "opencoat_runtime_daemon.config",
        "opencoat_runtime_daemon.config.loader",
    ],
)
def test_module_imports(modname: str) -> None:
    importlib.import_module(modname)


def test_default_config_loads() -> None:
    from opencoat_runtime_daemon.config import load_config

    cfg = load_config()
    assert cfg.runtime.schema_version == "0.2"
    assert cfg.storage.concern_store.kind == "memory"
    assert cfg.llm.provider == "stub"
    assert cfg.ipc.inproc.enabled is True


def test_check_config_cli_branch(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from opencoat_runtime_daemon.__main__ import main

    rc = main(["--check-config"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "config OK" in out
