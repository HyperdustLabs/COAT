"""Tests for the OpenCOAT CLI startup banner (DX sprint)."""

from __future__ import annotations

import pytest


def test_banner_shown_when_tty_and_no_guards(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from opencoat_runtime_cli import main as main_mod

    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(main_mod.sys.stdout, "isatty", lambda: True)
    rc = main_mod.main(["inspect", "joinpoints"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "____" in out and "_____" in out  # pyfiglet ``big`` OpenCOAT body
    assert "Open Concern-Oriented Agent Thinking" in out
    assert "M4 daemon:" in out
    assert "profile:" in out and "host plugins:" in out


def test_banner_suppressed_no_banner_flag(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from opencoat_runtime_cli import main as main_mod

    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(main_mod.sys.stdout, "isatty", lambda: True)
    rc = main_mod.main(["--no-banner", "inspect", "joinpoints"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Open Concern-Oriented Agent Thinking" not in out
    assert "before_response" in out


def test_banner_suppressed_when_no_color_set(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from opencoat_runtime_cli import main as main_mod

    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setattr(main_mod.sys.stdout, "isatty", lambda: True)
    rc = main_mod.main(["inspect", "joinpoints"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "M4 daemon:" not in out
    assert "before_response" in out


def test_banner_suppressed_not_tty(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from opencoat_runtime_cli import main as main_mod

    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(main_mod.sys.stdout, "isatty", lambda: False)
    rc = main_mod.main(["inspect", "joinpoints"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "M4 daemon:" not in out


def test_no_banner_can_appear_after_subcommand_name(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from opencoat_runtime_cli import main as main_mod

    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(main_mod.sys.stdout, "isatty", lambda: True)
    rc = main_mod.main(["inspect", "--no-banner", "joinpoints"])
    assert rc == 0
    assert "M4 daemon:" not in capsys.readouterr().out


class TestStripNoBannerFlag:
    """Pin POSIX ``--`` semantics for the pre-parse stripper (Codex P2 #36)."""

    def test_strips_global_flag(self) -> None:
        from opencoat_runtime_cli.main import _strip_no_banner_flag

        rest, no_banner = _strip_no_banner_flag(["--no-banner", "inspect", "joinpoints"])
        assert no_banner is True
        assert rest == ["inspect", "joinpoints"]

    def test_strips_flag_between_subcommand_and_positional(self) -> None:
        from opencoat_runtime_cli.main import _strip_no_banner_flag

        rest, no_banner = _strip_no_banner_flag(["inspect", "--no-banner", "joinpoints"])
        assert no_banner is True
        assert rest == ["inspect", "joinpoints"]

    def test_double_dash_freezes_remaining_argv(self) -> None:
        """After ``--`` the stripper must not touch literal ``--no-banner``."""
        from opencoat_runtime_cli.main import _strip_no_banner_flag

        rest, no_banner = _strip_no_banner_flag(["replay", "--", "--no-banner", "session.jsonl"])
        assert no_banner is False
        assert rest == ["replay", "--", "--no-banner", "session.jsonl"]

    def test_pre_double_dash_flag_still_stripped(self) -> None:
        """Only post-``--`` tokens are preserved; pre-``--`` flag still removed."""
        from opencoat_runtime_cli.main import _strip_no_banner_flag

        rest, no_banner = _strip_no_banner_flag(["--no-banner", "replay", "--", "--no-banner"])
        assert no_banner is True
        assert rest == ["replay", "--", "--no-banner"]
