"""M0 smoke tests — CLI dispatcher + inspect joinpoints."""

from __future__ import annotations

import importlib

import pytest


@pytest.mark.parametrize(
    "modname",
    [
        "opencoat_runtime_cli",
        "opencoat_runtime_cli.main",
        "opencoat_runtime_cli.commands",
        "opencoat_runtime_cli.commands.runtime_cmd",
        "opencoat_runtime_cli.commands.concern_cmd",
        "opencoat_runtime_cli.commands.dcn_cmd",
        "opencoat_runtime_cli.commands.replay_cmd",
        "opencoat_runtime_cli.commands.inspect_cmd",
        "opencoat_runtime_cli.commands.plugin_cmd",
        "opencoat_runtime_cli.demo_concerns",
        "opencoat_runtime_cli.plugin_templates",
        "opencoat_runtime_cli.plugin_templates.openclaw",
        "opencoat_runtime_cli.plugin_templates.custom",
        "opencoat_runtime_cli.visualize",
        "opencoat_runtime_cli.visualize.dcn_dot",
    ],
)
def test_module_imports(modname: str) -> None:
    importlib.import_module(modname)


def test_help_works() -> None:
    from opencoat_runtime_cli.main import build_parser

    parser = build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["--help"])
    assert exc.value.code == 0


def test_inspect_joinpoints(capsys: pytest.CaptureFixture[str]) -> None:
    from opencoat_runtime_cli.main import main

    rc = main(["inspect", "joinpoints"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "before_response" in out
    assert "lifecycle" in out
