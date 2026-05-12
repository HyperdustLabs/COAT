"""M0 smoke tests — CLI dispatcher + inspect joinpoints."""

from __future__ import annotations

import importlib

import pytest


@pytest.mark.parametrize(
    "modname",
    [
        "COAT_runtime_cli",
        "COAT_runtime_cli.main",
        "COAT_runtime_cli.commands",
        "COAT_runtime_cli.commands.runtime_cmd",
        "COAT_runtime_cli.commands.concern_cmd",
        "COAT_runtime_cli.commands.dcn_cmd",
        "COAT_runtime_cli.commands.replay_cmd",
        "COAT_runtime_cli.commands.inspect_cmd",
        "COAT_runtime_cli.commands.plugin_cmd",
        "COAT_runtime_cli.plugin_templates",
        "COAT_runtime_cli.plugin_templates.openclaw",
        "COAT_runtime_cli.plugin_templates.custom",
        "COAT_runtime_cli.visualize",
        "COAT_runtime_cli.visualize.dcn_dot",
    ],
)
def test_module_imports(modname: str) -> None:
    importlib.import_module(modname)


def test_help_works() -> None:
    from COAT_runtime_cli.main import build_parser

    parser = build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["--help"])
    assert exc.value.code == 0


def test_inspect_joinpoints(capsys: pytest.CaptureFixture[str]) -> None:
    from COAT_runtime_cli.main import main

    rc = main(["inspect", "joinpoints"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "before_response" in out
    assert "lifecycle" in out
