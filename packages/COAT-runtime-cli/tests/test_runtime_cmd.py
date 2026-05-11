"""Tests for ``COATr runtime up | down | status`` (M4 PR-21)."""

from __future__ import annotations

import argparse
import errno
import os
import signal
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from COAT_runtime_cli.commands import runtime_cmd
from COAT_runtime_daemon import build_runtime
from COAT_runtime_daemon.config import load_config
from COAT_runtime_daemon.ipc.http_server import HttpServer
from COAT_runtime_daemon.ipc.jsonrpc_dispatch import JsonRpcHandler

# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _ns(**kw: object) -> argparse.Namespace:
    defaults: dict[str, object] = {
        "action": "status",
        "config": None,
        "pid_file": None,
        "host": "127.0.0.1",
        "port": 7878,
        "path": "/rpc",
        "wait_seconds": 2.0,
        "log_level": "WARNING",
        "detach": True,
        "force": False,
    }
    defaults.update(kw)
    return argparse.Namespace(**defaults)


@pytest.fixture
def in_proc_server() -> Iterator[HttpServer]:
    with build_runtime(load_config(), env={}) as built:
        rpc = JsonRpcHandler(built.runtime)
        srv = HttpServer(rpc, host="127.0.0.1", port=0, path="/rpc")
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        time.sleep(0.05)
        try:
            yield srv
        finally:
            srv.shutdown()
            t.join(timeout=5)
            srv.server_close()


# ----------------------------------------------------------------------
# status
# ----------------------------------------------------------------------


def test_status_running_returns_zero(
    in_proc_server: HttpServer, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = runtime_cmd._handle(
        _ns(action="status", port=in_proc_server.port, host=in_proc_server.host)
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "running" in out
    assert f"{in_proc_server.host}:{in_proc_server.port}/rpc" in out


def test_status_stopped_returns_three(capsys: pytest.CaptureFixture[str]) -> None:
    rc = runtime_cmd._handle(_ns(action="status", port=1, wait_seconds=0.2))
    out = capsys.readouterr().out
    assert rc == 3
    assert "stopped" in out


def test_status_includes_pid_file_state(
    in_proc_server: HttpServer, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pid = tmp_path / "coat.pid"
    pid.write_text(f"{os.getpid()}\n")
    rc = runtime_cmd._handle(
        _ns(
            action="status",
            port=in_proc_server.port,
            host=in_proc_server.host,
            pid_file=pid,
        )
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert f"pid={os.getpid()}" in out
    assert "alive" in out


# ----------------------------------------------------------------------
# up / down round-trip (real subprocess daemon)
# ----------------------------------------------------------------------


def _write_http_config(tmp_path: Path, port: int) -> Path:
    cfg = tmp_path / "daemon.yaml"
    cfg.write_text(
        f"ipc:\n  http:\n    enabled: true\n    host: 127.0.0.1\n    port: {port}\n    path: /rpc\n"
    )
    return cfg


def _wait_until_gone(pid: int, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except OSError as exc:
            if exc.errno == errno.ESRCH:
                return True
        time.sleep(0.05)
    return False


def test_up_then_status_then_down(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    port = _free_port()
    cfg = _write_http_config(tmp_path, port)
    pid_file = tmp_path / "coat.pid"

    up_args = _ns(
        action="up",
        config=cfg,
        pid_file=pid_file,
        host="127.0.0.1",
        port=port,
        path="/rpc",
        wait_seconds=15.0,
    )
    spawned_pid: int | None = None
    try:
        rc_up = runtime_cmd._handle(up_args)
        captured = capsys.readouterr()
        assert rc_up == 0, captured
        assert pid_file.exists()
        spawned_pid = int(pid_file.read_text().strip())
        assert f"pid={spawned_pid}" in captured.out

        rc_status = runtime_cmd._handle(
            _ns(
                action="status",
                host="127.0.0.1",
                port=port,
                path="/rpc",
                pid_file=pid_file,
            )
        )
        assert rc_status == 0

        rc_down = runtime_cmd._handle(_ns(action="down", pid_file=pid_file, wait_seconds=15.0))
        assert rc_down == 0
        assert _wait_until_gone(spawned_pid, timeout=5.0)
    finally:
        # If anything above leaked the daemon, clean up so the test
        # process doesn't hang at exit. The daemon was orphaned to init
        # in `up`, so a stray SIGKILL is the safest cleanup.
        if pid_file.exists():
            try:
                stuck = int(pid_file.read_text().strip())
                if _wait_until_gone(stuck, timeout=0) is False:
                    os.kill(stuck, signal.SIGKILL)
            except (OSError, ValueError):
                pass


def test_up_when_already_running_is_noop(
    in_proc_server: HttpServer, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = runtime_cmd._handle(
        _ns(
            action="up",
            host=in_proc_server.host,
            port=in_proc_server.port,
            path="/rpc",
            pid_file=tmp_path / "coat.pid",
        )
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "already running" in out


def _serve_foreign_http(port: int) -> tuple[threading.Thread, object]:
    """Bind a tiny HTTP server that answers every request with 404.

    Used to simulate "something else is on this port" — the daemon we
    spawn from `runtime up` is *not* what's listening, so the CLI must
    refuse to spawn instead of saying "already running" (Codex P1).
    """
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class _Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            self.send_error(404, "not us")

        def do_GET(self) -> None:
            self.send_error(404, "not us")

        def log_message(self, *_a: object) -> None:
            return

    srv = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return t, srv


def test_up_refuses_to_spawn_over_foreign_listener(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Codex P1 on PR-21: a port occupied by another HTTP service must
    surface as a hard error, not "already running"."""
    port = _free_port()
    t, srv = _serve_foreign_http(port)
    try:
        rc = runtime_cmd._handle(
            _ns(
                action="up",
                host="127.0.0.1",
                port=port,
                path="/rpc",
                pid_file=tmp_path / "coat.pid",
                wait_seconds=0.2,
            )
        )
    finally:
        srv.shutdown()  # type: ignore[attr-defined]
        srv.server_close()  # type: ignore[attr-defined]
        t.join(timeout=5)

    captured = capsys.readouterr()
    assert rc == 1
    assert "already running" not in captured.out
    assert "another service" in captured.err
    # PID file untouched — no spawn happened.
    assert not (tmp_path / "coat.pid").exists()


def test_up_detached_without_fork_returns_clean_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Codex P2 on PR-21: on platforms without ``os.fork`` the default
    --detach invocation must exit cleanly instead of tracebacking."""
    monkeypatch.delattr(os, "fork", raising=False)
    rc = runtime_cmd._handle(
        _ns(
            action="up",
            host="127.0.0.1",
            port=1,  # nothing listening here
            path="/rpc",
            pid_file=tmp_path / "coat.pid",
            wait_seconds=0.2,
            detach=True,
        )
    )
    err = capsys.readouterr().err
    assert rc == 2
    assert "--detach requires" in err
    assert "--foreground" in err
    assert not (tmp_path / "coat.pid").exists()


# ----------------------------------------------------------------------
# down edge cases
# ----------------------------------------------------------------------


def test_down_without_pid_file_returns_two(capsys: pytest.CaptureFixture[str]) -> None:
    rc = runtime_cmd._handle(_ns(action="down"))
    err = capsys.readouterr().err
    assert rc == 2
    assert "--pid-file" in err


def test_down_missing_pid_file_is_zero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = runtime_cmd._handle(_ns(action="down", pid_file=tmp_path / "missing.pid"))
    out = capsys.readouterr().out
    assert rc == 0
    assert "no daemon pid" in out


def test_down_dead_pid_is_zero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    pid_file = tmp_path / "stale.pid"
    pid_file.write_text("2147483646\n")  # almost certainly not running
    rc = runtime_cmd._handle(_ns(action="down", pid_file=pid_file))
    out = capsys.readouterr().out
    assert rc == 0
    assert "not alive" in out


# ----------------------------------------------------------------------
# reload (deferred)
# ----------------------------------------------------------------------


def test_reload_is_deferred(capsys: pytest.CaptureFixture[str]) -> None:
    rc = runtime_cmd._handle(_ns(action="reload"))
    err = capsys.readouterr().err
    assert rc == 2
    assert "not yet exposed" in err


# ----------------------------------------------------------------------
# argparse wiring
# ----------------------------------------------------------------------


def test_register_attaches_func() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers()
    runtime_cmd.register(sub)
    args = parser.parse_args(["runtime", "status"])
    assert args.func is runtime_cmd._handle
    assert args.action == "status"
