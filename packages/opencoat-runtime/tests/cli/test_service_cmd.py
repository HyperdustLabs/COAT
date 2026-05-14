"""Unit tests for ``opencoat service`` manifest generation."""

from __future__ import annotations

import shlex
from pathlib import Path

from opencoat_runtime_cli.commands import service_cmd


def test_plist_payload_pins_home_relative_pid(tmp_path: Path) -> None:
    home = tmp_path / "u"
    (home / ".opencoat").mkdir(parents=True)
    payload = service_cmd._plist_payload(home=home, python_exe="/fake/bin/python", config=None)
    want = str((home / ".opencoat" / "opencoat.pid").resolve())
    assert want in payload["ProgramArguments"]
    assert payload["EnvironmentVariables"]["OPENCOAT_PID_FILE"] == want


def test_systemd_unit_contains_exec_and_pid(tmp_path: Path) -> None:
    home = tmp_path / "u"
    text = service_cmd._systemd_unit_text(home=home, python_exe="/x/python", config=None)
    pid = str((home / ".opencoat" / "opencoat.pid").resolve())
    assert f'Environment="OPENCOAT_PID_FILE={pid}"' in text
    want_exec = "ExecStart=" + shlex.join(
        ["/x/python", "-m", "opencoat_runtime_daemon", "--pid-file", pid]
    )
    assert want_exec in text
    assert f'WorkingDirectory="{home.resolve()}"' in text


def test_systemd_unit_quotes_paths_with_spaces(tmp_path: Path) -> None:
    home = tmp_path / "home dir"
    py = tmp_path / "py bin" / "python"
    py.parent.mkdir(parents=True)
    text = service_cmd._systemd_unit_text(home=home, python_exe=str(py), config=None)
    pid = str((home / ".opencoat" / "opencoat.pid").resolve())
    want_exec = "ExecStart=" + shlex.join(
        [str(py), "-m", "opencoat_runtime_daemon", "--pid-file", pid]
    )
    assert want_exec in text
    assert "'" in want_exec or '"' in want_exec
