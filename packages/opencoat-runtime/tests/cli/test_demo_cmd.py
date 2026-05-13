"""Tests for ``opencoat demo`` — the zero-paste 3-scene pickup tour."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest
from opencoat_runtime_cli.commands import demo_cmd
from opencoat_runtime_cli.main import main as opencoat_main

# ---------------------------------------------------------------------------
# argparse wiring + help surface
# ---------------------------------------------------------------------------


class TestDemoCommandRegistration:
    """Pin that ``opencoat demo`` shows up in ``--help`` and that its own
    ``--help`` advertises the two modes users care about (``--in-proc``
    + ``--script-out``).
    """

    def test_demo_subcommand_appears_in_root_help(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit):
            opencoat_main(["--no-banner", "--help"])
        out = capsys.readouterr().out
        assert " demo " in out  # listed in subcommand table

    def test_demo_help_advertises_both_modes(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit):
            opencoat_main(["--no-banner", "demo", "--help"])
        out = capsys.readouterr().out
        assert "--in-proc" in out
        assert "--script-out" in out


# ---------------------------------------------------------------------------
# In-process mode — the cold-tour path
# ---------------------------------------------------------------------------


class TestInProcMode:
    """``--in-proc`` is the "I just want to see what this thing does"
    button: no ``opencoat runtime up``, no ``opencoat concern import``,
    just three scenes against an embedded runtime.
    """

    def test_three_scenes_all_show_visible_change(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc = opencoat_main(["--no-banner", "demo", "--in-proc"])
        assert rc == 0
        out = capsys.readouterr().out
        # Header points at the in-proc topology so users know what
        # they're looking at without scrolling to the bottom.
        assert "in-proc" in out

        # Scene 1 — prompt folding
        assert "PROMPT FOLDING" in out
        assert "demo-prompt-prefix" in out
        # The actual injected text reaches the prompt slot — this is
        # the line that lets users see "concerns changed my agent".
        assert "[OpenCOAT demo active]" in out

        # Scene 2 — tool guard
        assert "TOOL GUARD" in out
        assert "demo-tool-block" in out
        assert "BLOCKED" in out
        assert "rm -rf" in out

        # Scene 3 — memory note
        assert "MEMORY NOTE" in out
        assert "demo-memory-tag" in out
        assert "memory.policy=demo-memory-tag" in out

        # Closing "all green" affordance.
        assert "All three scenes produced visible host-context changes" in out

    def test_in_proc_seeds_demo_concerns_without_any_external_call(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Critical UX promise: ``opencoat demo --in-proc`` works
        cold. No daemon, no prior ``opencoat concern import --demo``.
        Pinning this by running with an obviously-not-running daemon
        URL — ``--in-proc`` must not even try to dial it.
        """
        rc = opencoat_main(
            [
                "--no-banner",
                "demo",
                "--in-proc",
                "--host",
                "127.0.0.1",
                "--port",
                "9",  # discard port — would fail instantly if dialled
            ]
        )
        assert rc == 0
        out = capsys.readouterr().out
        assert "could not reach the daemon" not in out
        assert "All three scenes" in out


# ---------------------------------------------------------------------------
# Daemon path — unreachable case (the reachable case is covered by the
# live smoke in the PR description; replicating it here would need a
# fake HTTP server, which is overkill for what's already a thin wrapper
# around ``Client.connect`` + ``install_hooks``).
# ---------------------------------------------------------------------------


class TestDaemonUnreachable:
    def test_friendly_hint_when_daemon_down(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Port 9 (discard) is reserved and reliably refuses connections.
        rc = opencoat_main(
            [
                "--no-banner",
                "demo",
                "--host",
                "127.0.0.1",
                "--port",
                "9",
                "--path",
                "/rpc",
            ]
        )
        assert rc == 2
        err = capsys.readouterr().err
        # Both halves of the hint should land on the user's terminal:
        # what's wrong + how to fix it (with the daemon-less alternative).
        assert "could not reach the daemon" in err
        assert "opencoat runtime up" in err
        assert "opencoat demo --in-proc" in err


# ---------------------------------------------------------------------------
# --script-out — runnable template path
# ---------------------------------------------------------------------------


class TestScriptOut:
    def test_script_out_writes_file_and_exits_without_running(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        out_path = tmp_path / "demo_host.py"
        rc = opencoat_main(["--no-banner", "demo", "--script-out", str(out_path)])
        assert rc == 0
        assert out_path.exists()
        out = capsys.readouterr().out
        # ``--script-out`` is "write and exit", so the scene runner
        # output should NOT be on stdout.
        assert "PROMPT FOLDING" not in out
        assert "wrote" in out
        assert str(out_path) in out

    def test_script_out_is_syntactically_valid_python(self, tmp_path: Path) -> None:
        """The dumped template must be a runnable Python file — parse
        it with :mod:`ast` so a copy-paste bug in the template surfaces
        immediately (not on a user's terminal).
        """
        out_path = tmp_path / "demo_host.py"
        opencoat_main(["--no-banner", "demo", "--script-out", str(out_path)])
        source = out_path.read_text()
        ast.parse(source)  # raises SyntaxError if the template is broken

    def test_script_out_template_uses_pickup_api(self, tmp_path: Path) -> None:
        """Pin the canonical surface so future template edits don't
        accidentally drop the demo back to "emit + print activation"
        which is what we just removed.
        """
        out_path = tmp_path / "demo_host.py"
        opencoat_main(["--no-banner", "demo", "--script-out", str(out_path)])
        text = out_path.read_text()
        assert "install_hooks" in text
        assert "apply_to" in text
        assert "guard_tool_call" in text
        # Old "JoinpointEmitter then print activation_log" pattern
        # — explicitly forbidden so we don't regress the demo shape.
        assert "JoinpointEmitter" not in text

    def test_script_out_embeds_resolved_daemon_url(self, tmp_path: Path) -> None:
        out_path = tmp_path / "demo_host.py"
        opencoat_main(
            [
                "--no-banner",
                "demo",
                "--script-out",
                str(out_path),
                "--host",
                "example.com",
                "--port",
                "8123",
                "--path",
                "/v1/opencoat",
            ]
        )
        text = out_path.read_text()
        # ``repr()`` may use either quote style depending on the URL —
        # don't pin which one ``str.format`` produced.
        assert "http://example.com:8123/v1/opencoat" in text
        assert "DAEMON_URL =" in text

    def test_script_out_creates_parent_dirs(self, tmp_path: Path) -> None:
        """Convenience: ``--script-out a/b/c/demo_host.py`` should just
        work, not error with "no such directory".
        """
        out_path = tmp_path / "nested" / "dir" / "demo_host.py"
        rc = opencoat_main(["--no-banner", "demo", "--script-out", str(out_path)])
        assert rc == 0
        assert out_path.exists()

    def test_generated_script_is_runnable_offline(self, tmp_path: Path) -> None:
        """The dumped script imports the host SDK at module top, so
        even without a daemon we should be able to ``python -c "import
        ast; ast.parse(...)"`` and at least ``python -m py_compile`` it.
        Catches missing imports / typos in the template.
        """
        out_path = tmp_path / "demo_host.py"
        opencoat_main(["--no-banner", "demo", "--script-out", str(out_path)])
        # ``py_compile`` is the cheapest "this would import cleanly if
        # the runtime were up" check — it parses + byte-compiles
        # without actually executing module-level code.
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(out_path)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------------
# Hint-string contract — kept module-level so the skill repo can
# reference them with confidence and we get a CI-level signal if the
# wording drifts.
# ---------------------------------------------------------------------------


class TestHintStrings:
    def test_daemon_unreachable_hint_advertises_both_recovery_paths(self) -> None:
        hint = demo_cmd.DAEMON_UNREACHABLE_HINT
        assert "opencoat runtime up" in hint
        assert "opencoat concern import --demo" in hint
        assert "--in-proc" in hint

    def test_host_sdk_missing_hint_advertises_pipx_inject(self) -> None:
        hint = demo_cmd.HOST_SDK_MISSING_HINT
        assert "opencoat-runtime-host" in hint
        assert "pipx inject" in hint or "pip install" in hint

    def test_no_concerns_hint_points_at_concern_import(self) -> None:
        hint = demo_cmd.NO_CONCERNS_SEEDED_HINT
        assert "opencoat concern import --demo" in hint
