"""Tests for ``opencoat plugin install <host>`` scaffolding (DX sprint)."""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Any

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


class TestScaffoldExposesDaemonBackedSurface:
    """The 0.1.0 scaffold ships two install paths: daemon-backed (the
    default, paired with ``opencoat runtime up``) and in-process. The
    daemon-backed path is what the ``opencoat-skill`` demo flow expects.
    These tests pin the public surface so the skill's copy-paste
    instructions can't go stale.
    """

    def test_openclaw_scaffold_exposes_daemon_install_and_legacy_install(self) -> None:
        from opencoat_runtime_cli.plugin_templates.openclaw import bootstrap_opencoat

        # Daemon-backed entry points.
        assert callable(bootstrap_opencoat.install)
        assert callable(bootstrap_opencoat.daemon_client)
        assert bootstrap_opencoat.DEFAULT_DAEMON_URL == "http://127.0.0.1:7878"
        # Legacy in-process path is still available, renamed to make
        # the daemon-vs-embedded choice explicit at the call site.
        assert callable(bootstrap_opencoat.install_in_process)
        assert callable(bootstrap_opencoat.build_runtime)
        assert callable(bootstrap_opencoat.seed_stores)
        # The events the adapter subscribes to are unchanged; pinned by
        # the reachability test below.
        assert bootstrap_opencoat.DEFAULT_EVENT_NAMES == (
            "agent.started",
            "agent.user_message",
            "agent.memory_write",
        )

    def test_custom_scaffold_exposes_daemon_client_helper(self) -> None:
        from opencoat_runtime_cli.plugin_templates.custom import bootstrap_opencoat

        assert callable(bootstrap_opencoat.daemon_client)
        assert bootstrap_opencoat.DEFAULT_DAEMON_URL == "http://127.0.0.1:7878"
        # In-process path stays available for tests / scripts.
        assert callable(bootstrap_opencoat.build_runtime_with_adapter)

    def test_openclaw_daemon_client_honours_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from opencoat_runtime_cli.plugin_templates.openclaw import bootstrap_opencoat
        from opencoat_runtime_host_sdk.transport.http import HttpTransport

        monkeypatch.setenv("OPENCOAT_DAEMON_URL", "http://10.0.0.7:9999")
        client = bootstrap_opencoat.daemon_client()
        assert isinstance(client.transport, HttpTransport)
        assert client.transport.endpoint == "http://10.0.0.7:9999/rpc"

    def test_openclaw_daemon_client_explicit_url_wins(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from opencoat_runtime_cli.plugin_templates.openclaw import bootstrap_opencoat

        monkeypatch.setenv("OPENCOAT_DAEMON_URL", "http://from-env:1")
        client = bootstrap_opencoat.daemon_client("http://explicit:2")
        assert client.transport.endpoint == "http://explicit:2/rpc"

    def test_custom_scaffold_imports_without_host_sdk(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The custom scaffold must be importable in a runtime-only
        install (no ``opencoat-runtime-host`` on path).

        ``opencoat-runtime`` does not declare ``opencoat-runtime-host``
        as a dependency, so users on a ``pipx install opencoat-runtime``
        topology must still be able to ``import bootstrap_opencoat``
        and use :func:`build_runtime_with_adapter` for the in-process
        path. Only :func:`daemon_client` actually needs the host SDK,
        and pays the import cost lazily.
        """
        # Pretend the host SDK is uninstalled.
        monkeypatch.setitem(sys.modules, "opencoat_runtime_host_sdk", None)
        # Force a re-import so the top-of-file import block re-runs
        # under the simulated missing-package state.
        sys.modules.pop(
            "opencoat_runtime_cli.plugin_templates.custom.bootstrap_opencoat",
            None,
        )

        from opencoat_runtime_cli.plugin_templates.custom import bootstrap_opencoat

        # In-process path still works — that's the whole point of the
        # lazy import. We don't actually call build_runtime_with_adapter
        # here because the runtime + LLM stub paths are exercised
        # elsewhere; we just want to prove the module loaded.
        assert callable(bootstrap_opencoat.build_runtime_with_adapter)
        assert callable(bootstrap_opencoat.build_runtime)

        # daemon_client is still exposed (for type discovery / docs),
        # but calling it without the host SDK fails *at call time*,
        # not at import time, with the same error the user would get
        # from ``from opencoat_runtime_host_sdk import Client``.
        with pytest.raises((ModuleNotFoundError, ImportError)):
            bootstrap_opencoat.daemon_client()

    def test_openclaw_daemon_runtime_proxy_forwards_to_client(self) -> None:
        """The :class:`_DaemonRuntime` proxy must satisfy ``RuntimeLike``
        and forward every :meth:`on_joinpoint` call to ``client.emit``.
        """
        from opencoat_runtime_cli.plugin_templates.openclaw.bootstrap_opencoat import (
            _DaemonRuntime,
        )
        from opencoat_runtime_host_openclaw.hooks import RuntimeLike

        captured: list[tuple[Any, dict[str, Any]]] = []

        class _FakeClient:
            def emit(self, jp, **kw):  # type: ignore[no-untyped-def]
                captured.append((jp, kw))
                return "sentinel"

        proxy = _DaemonRuntime(_FakeClient())  # type: ignore[arg-type]
        # Pin both the structural Protocol satisfaction and the
        # forwarding semantics — these are the two things install_hooks
        # relies on when ``install()`` wires the proxy in for the
        # daemon-backed path.
        assert isinstance(proxy, RuntimeLike)
        out = proxy.on_joinpoint("jp-fake", context={"k": "v"}, return_none_when_empty=True)  # type: ignore[arg-type]
        assert out == "sentinel"
        assert captured == [("jp-fake", {"context": {"k": "v"}, "return_none_when_empty": True})]


class TestPluginInstallNextOutput:
    """Pin the post-install ``Next:`` guidance so users see the
    daemon-first flow that matches the ``opencoat-skill`` demo, not
    the legacy in-process call.
    """

    def test_openclaw_next_steps_lead_with_runtime_up(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        capsys.readouterr()
        _scaffold_dir(tmp_path, "openclaw")
        out = capsys.readouterr().out
        assert "opencoat runtime up" in out
        assert "opencoat concern import --demo" in out
        assert "bootstrap_opencoat.install" in out
        # The in-process path is still mentioned as an alternative.
        assert "install_in_process" in out
        # The pickup API — the half M5 #31 left half-wired — must
        # appear in the post-install hint so users see the full
        # event → apply_to / guard_tool_call loop, not just the
        # ``install()`` call that subscribes to events.
        assert "apply_to" in out
        assert "guard_tool_call" in out

    def test_custom_next_steps_lead_with_runtime_up(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        capsys.readouterr()
        _scaffold_dir(tmp_path, "custom")
        out = capsys.readouterr().out
        assert "opencoat runtime up" in out
        assert "daemon_client" in out
        assert "client.emit" in out
