"""Tests for the OpenCOAT CLI startup banner (DX sprint)."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator

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


# ---------------------------------------------------------------------------
# llm suffix on the banner status line  (release-readiness)
# ---------------------------------------------------------------------------


@pytest.fixture
def stub_fallback_server() -> Iterator[tuple[str, int]]:
    """Spin a real daemon HTTP server with ``provider: auto`` + empty env.

    Empty env → auto-detection falls back to stub-fallback. We expose
    the live ``(host, port)`` so the test can point the CLI banner
    probe at it.
    """
    from opencoat_runtime_daemon import build_runtime
    from opencoat_runtime_daemon.config import load_config
    from opencoat_runtime_daemon.ipc.http_server import HttpServer
    from opencoat_runtime_daemon.ipc.jsonrpc_dispatch import JsonRpcHandler

    with build_runtime(load_config(), env={}) as built:
        rpc = JsonRpcHandler(built.runtime, llm_info=built.llm_info)
        srv = HttpServer(rpc, host="127.0.0.1", port=0, path="/rpc")
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        time.sleep(0.05)
        try:
            yield srv.host, srv.port
        finally:
            srv.shutdown()
            t.join(timeout=5)
            srv.server_close()


@pytest.fixture
def real_provider_server() -> Iterator[tuple[str, int]]:
    """Same as ``stub_fallback_server`` but with a synthetic real-provider
    ``LLMInfo`` injected into the handler, so we can pin the
    happy-path label without needing a real OpenAI key.
    """
    from opencoat_runtime_daemon import LLMInfo, build_runtime
    from opencoat_runtime_daemon.config import load_config
    from opencoat_runtime_daemon.ipc.http_server import HttpServer
    from opencoat_runtime_daemon.ipc.jsonrpc_dispatch import JsonRpcHandler

    with build_runtime(load_config(), env={}) as built:
        info = LLMInfo(
            label="openai/gpt-4o-mini",
            kind="openai",
            real=True,
            requested="auto",
        )
        rpc = JsonRpcHandler(built.runtime, llm_info=info)
        srv = HttpServer(rpc, host="127.0.0.1", port=0, path="/rpc")
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        time.sleep(0.05)
        try:
            yield srv.host, srv.port
        finally:
            srv.shutdown()
            t.join(timeout=5)
            srv.server_close()


def _resolve_to(host: str, port: int, monkeypatch: pytest.MonkeyPatch) -> None:
    """Monkeypatch ``resolve_endpoint`` so the banner probes ``host:port``."""
    from opencoat_runtime_cli import _http as http_mod

    def _resolve(_args: object) -> tuple[str, int, str]:
        return host, port, "/rpc"

    monkeypatch.setattr(http_mod, "resolve_endpoint", _resolve)


def test_banner_shows_degraded_label_when_daemon_on_stub_fallback(
    stub_fallback_server: tuple[str, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Banner must call out stub-fallback so users never get to
    ``concern extract`` and wonder why 0 candidates come back.
    """
    from opencoat_runtime_cli import main as main_mod

    _resolve_to(*stub_fallback_server, monkeypatch=monkeypatch)
    line = main_mod._daemon_status_line()
    assert "status: healthy" in line
    assert "llm: stub-fallback" in line
    assert "degraded" in line


def test_banner_shows_real_provider_label_when_daemon_is_healthy(
    real_provider_server: tuple[str, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from opencoat_runtime_cli import main as main_mod

    _resolve_to(*real_provider_server, monkeypatch=monkeypatch)
    line = main_mod._daemon_status_line()
    assert "status: healthy" in line
    assert "llm: openai/gpt-4o-mini" in line
    assert "degraded" not in line


def test_banner_silently_drops_llm_suffix_when_probe_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An older daemon predating ``runtime.llm_info`` must not break
    the banner — we just elide the ``llm: …`` suffix.
    """
    from opencoat_runtime_cli import main as main_mod

    class _Probe:
        endpoint = "http://example/rpc"

        def call(self, method: str, *_a: object, **_k: object):
            if method == "runtime.llm_info":
                from opencoat_runtime_cli.transport import HttpRpcCallError

                raise HttpRpcCallError(code=-32601, message="method not found")
            return {"ok": True}

    # We don't want to actually go to network — exercise the suffix
    # helper directly.
    suffix = main_mod._daemon_llm_suffix(_Probe())
    assert suffix == ""
