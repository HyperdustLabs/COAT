"""Unit tests for ``opencoat service`` manifest generation."""

from __future__ import annotations

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
    assert f"Environment=OPENCOAT_PID_FILE={pid}" in text
    assert f"--pid-file {pid}" in text
    assert "ExecStart=/x/python -m opencoat_runtime_daemon" in text
