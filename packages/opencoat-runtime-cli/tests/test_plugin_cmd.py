"""Tests for ``COATr plugin install <host>`` scaffolding (DX sprint)."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest
from opencoat_runtime_cli.commands import plugin_cmd
from opencoat_runtime_cli.main import main as cli_main

EXPECTED_FILES = ("__init__.py", "bootstrap_opencoat.py", "host_adapter.py", "concerns.py")


def _scaffold_dir(tmp_path: Path, host: str) -> Path:
    out = tmp_path / f"opencoat_plugin_{host}"
    rc = cli_main(["--no-banner", "plugin", "install", host, "--out", str(out)])
    assert rc == 0, f"plugin install {host} failed: rc={rc}"
    return out


class TestPluginInstall:
    @pytest.mark.parametrize("host", ["openclaw", "custom"])
    def test_install_writes_full_starter_set(self, tmp_path: Path, host: str) -> None:
        out = _scaffold_dir(tmp_path, host)
        for name in EXPECTED_FILES:
            assert (out / name).exists(), f"missing {name}"
            assert (out / name).stat().st_size > 0, f"{name} is empty"

    @pytest.mark.parametrize("host", ["openclaw", "custom"])
    def test_scaffold_files_are_syntactically_valid_python(self, tmp_path: Path, host: str) -> None:
        """The generated scaffold must parse as Python (no f-string drift)."""
        out = _scaffold_dir(tmp_path, host)
        for name in EXPECTED_FILES:
            text = (out / name).read_text(encoding="utf-8")
            ast.parse(text)  # raises SyntaxError if the template is broken

    @pytest.mark.parametrize("host", ["openclaw", "custom"])
    def test_scaffold_package_is_importable(self, tmp_path: Path, host: str) -> None:
        """Adding the parent dir to ``sys.path`` makes the scaffold importable."""
        out = _scaffold_dir(tmp_path, host)
        parent = str(out.parent)
        sys.path.insert(0, parent)
        pkg_name = out.name
        try:
            mod = __import__(pkg_name)
            assert mod.__doc__ is not None
            assert host in mod.__doc__
        finally:
            sys.path.remove(parent)
            for key in [k for k in sys.modules if k == pkg_name or k.startswith(f"{pkg_name}.")]:
                sys.modules.pop(key, None)

    def test_install_default_out_dir(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Without ``--out`` we land in ``./opencoat_plugin`` relative to cwd."""
        monkeypatch.chdir(tmp_path)
        rc = cli_main(["--no-banner", "plugin", "install", "openclaw"])
        assert rc == 0
        target = tmp_path / "opencoat_plugin"
        for name in EXPECTED_FILES:
            assert (target / name).exists()
        assert "wrote 4 files" in capsys.readouterr().out

    def test_install_blocks_overwrite_without_force(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        out = _scaffold_dir(tmp_path, "custom")
        capsys.readouterr()
        rc = cli_main(["--no-banner", "plugin", "install", "custom", "--out", str(out)])
        assert rc == 1
        err = capsys.readouterr().err
        assert "already exists" in err
        assert "--force" in err

    def test_install_force_overwrites(self, tmp_path: Path) -> None:
        out = _scaffold_dir(tmp_path, "openclaw")
        sentinel = "# sentinel-edit\n"
        (out / "concerns.py").write_text(sentinel, encoding="utf-8")
        rc = cli_main(
            ["--no-banner", "plugin", "install", "openclaw", "--out", str(out), "--force"]
        )
        assert rc == 0
        body = (out / "concerns.py").read_text(encoding="utf-8")
        assert body != sentinel
        assert "seed_concerns" in body

    def test_install_rejects_unknown_host(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """argparse ``choices`` reject the unknown host with exit code 2."""
        out = tmp_path / "ignored"
        with pytest.raises(SystemExit) as exc:
            cli_main(["--no-banner", "plugin", "install", "nothere", "--out", str(out)])
        assert exc.value.code == 2
        assert "invalid choice" in capsys.readouterr().err

    def test_install_partial_failure_writes_nothing(self, tmp_path: Path) -> None:
        """Pre-flight existence check runs before any file write."""
        out = tmp_path / "partial"
        out.mkdir()
        # Pre-populate the second-checked file; nothing else.
        existing = out / "host_adapter.py"
        existing.write_text("# preexisting\n", encoding="utf-8")

        rc = cli_main(["--no-banner", "plugin", "install", "custom", "--out", str(out)])
        assert rc == 1
        # We must NOT have written __init__.py / bootstrap_opencoat.py / concerns.py.
        assert not (out / "__init__.py").exists()
        assert not (out / "bootstrap_opencoat.py").exists()
        assert not (out / "concerns.py").exists()
        # Existing file untouched.
        assert existing.read_text(encoding="utf-8") == "# preexisting\n"


class TestPluginList:
    def test_list_emits_known_hosts(self, capsys: pytest.CaptureFixture[str]) -> None:
        rc = cli_main(["--no-banner", "plugin", "list"])
        assert rc == 0
        out = capsys.readouterr().out
        for name in plugin_cmd._AVAILABLE_HOSTS:
            assert name in out


class TestPluginDisable:
    def test_disable_is_stub_until_post_m6(self, capsys: pytest.CaptureFixture[str]) -> None:
        rc = cli_main(["--no-banner", "plugin", "disable", "some-name"])
        assert rc == 2
        assert "post-M6" in capsys.readouterr().err


class TestScaffoldJoinpointsAreReachable:
    """Pin the scaffold concerns to joinpoints that actually fire.

    Codex P2 on PR #37 flagged that ``on_request_received`` was unreachable
    via the OpenClaw adapter / default event subscription; this test pins
    the reachability invariant for both scaffolds so the regression cannot
    silently return.
    """

    def test_openclaw_concerns_reach_default_subscription(self) -> None:
        from opencoat_runtime_cli.plugin_templates.openclaw.bootstrap_opencoat import (
            DEFAULT_EVENT_NAMES,
        )
        from opencoat_runtime_cli.plugin_templates.openclaw.concerns import seed_concerns
        from opencoat_runtime_host_openclaw.joinpoint_map import OPENCLAW_EVENT_MAP

        reachable = {OPENCLAW_EVENT_MAP[name] for name in DEFAULT_EVENT_NAMES}
        for concern in seed_concerns():
            for jp in concern.pointcut.joinpoints:
                assert jp in reachable, (
                    f"concern {concern.id!r} uses joinpoint {jp!r} which is not "
                    f"emitted by the default OpenClaw event subscription "
                    f"({sorted(reachable)})"
                )

    def test_custom_concerns_reference_catalog_joinpoints(self) -> None:
        from opencoat_runtime_cli.plugin_templates.custom.concerns import seed_concerns
        from opencoat_runtime_core.joinpoint import JOINPOINT_CATALOG

        for concern in seed_concerns():
            for jp in concern.pointcut.joinpoints:
                assert jp in JOINPOINT_CATALOG, (
                    f"concern {concern.id!r} uses joinpoint {jp!r} which is not "
                    f"in the built-in JOINPOINT_CATALOG"
                )
