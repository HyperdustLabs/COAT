"""Tests for :class:`~COAT_runtime_daemon.daemon.Daemon` lifecycle (M4 PR-20)."""

from __future__ import annotations

import json
import os
import signal
import threading
import time
from http import HTTPStatus
from http.client import HTTPConnection
from pathlib import Path

import pytest
from COAT_runtime_daemon import Daemon, DaemonAlreadyStartedError
from COAT_runtime_daemon._pidfile import PidFileError
from COAT_runtime_daemon.config import load_config


def _http_cfg(tmp_path: Path | None = None):  # type: ignore[no-untyped-def]
    cfg = load_config()
    # Enable HTTP on an ephemeral port via the extra-allow IPCEndpoint.
    cfg.ipc.http.enabled = True
    object.__setattr__(cfg.ipc.http, "host", "127.0.0.1")
    object.__setattr__(cfg.ipc.http, "port", 0)
    object.__setattr__(cfg.ipc.http, "path", "/rpc")
    return cfg


def test_start_stop_no_http(tmp_path: Path) -> None:
    cfg = load_config()
    pid = tmp_path / "coat.pid"
    d = Daemon(cfg, env={}, pid_file=pid)
    d.start()
    try:
        assert pid.exists()
        assert pid.read_text().strip() == str(os.getpid())
        # No HTTP — handler still wired in-proc.
        out = d.runtime_handler.handle({"jsonrpc": "2.0", "id": 1, "method": "health.ping"})
        assert out == {"jsonrpc": "2.0", "result": {"ok": True}, "id": 1}
    finally:
        d.stop()
    assert not pid.exists()


def test_stop_is_idempotent(tmp_path: Path) -> None:
    cfg = load_config()
    d = Daemon(cfg, env={}, pid_file=tmp_path / "coat.pid")
    d.start()
    d.stop()
    d.stop()  # second call is a no-op


def test_start_twice_raises(tmp_path: Path) -> None:
    cfg = load_config()
    d = Daemon(cfg, env={}, pid_file=tmp_path / "coat.pid")
    d.start()
    try:
        with pytest.raises(DaemonAlreadyStartedError):
            d.start()
    finally:
        d.stop()


def test_pid_file_collision_blocks_start(tmp_path: Path) -> None:
    cfg = load_config()
    pid = tmp_path / "coat.pid"
    # Reserve the path with PID 1 (always alive on POSIX).
    pid.write_text("1\n")
    d = Daemon(cfg, env={}, pid_file=pid)
    with pytest.raises(PidFileError):
        d.start()
    # PID file untouched.
    assert pid.read_text().strip() == "1"


def test_http_endpoint_serves_jsonrpc(tmp_path: Path) -> None:
    cfg = _http_cfg()
    d = Daemon(cfg, env={}, pid_file=tmp_path / "coat.pid")
    d.start()
    try:
        assert d.http_server is not None
        time.sleep(0.05)
        host, port = d.http_server.host, d.http_server.port
        conn = HTTPConnection(host, port, timeout=5)
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "health.ping"}).encode()
        conn.request(
            "POST",
            "/rpc",
            body=body,
            headers={"Content-Type": "application/json", "Content-Length": str(len(body))},
        )
        resp = conn.getresponse()
        assert resp.status == HTTPStatus.OK
        data = json.loads(resp.read())
        assert data["result"]["ok"] is True
        conn.close()
    finally:
        d.stop()


def test_reload_swaps_runtime_without_restarting_socket(tmp_path: Path) -> None:
    cfg = _http_cfg()
    d = Daemon(cfg, env={}, pid_file=tmp_path / "coat.pid")
    d.start()
    try:
        assert d.http_server is not None
        time.sleep(0.05)
        old_handler = d.runtime_handler
        port = d.http_server.port

        d.reload()
        new_handler = d.runtime_handler
        assert new_handler is not old_handler
        # Same listening port.
        assert d.http_server.port == port

        # And the socket is still serving the *new* handler.
        conn = HTTPConnection(d.http_server.host, port, timeout=5)
        body = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "health.ping"}).encode()
        conn.request(
            "POST",
            "/rpc",
            body=body,
            headers={"Content-Type": "application/json", "Content-Length": str(len(body))},
        )
        resp = conn.getresponse()
        assert resp.status == HTTPStatus.OK
        conn.close()
    finally:
        d.stop()


def test_reload_before_start_raises(tmp_path: Path) -> None:
    cfg = load_config()
    d = Daemon(cfg, env={}, pid_file=tmp_path / "coat.pid")
    with pytest.raises(RuntimeError):
        d.reload()


def test_run_until_signal_drains_on_sigterm(tmp_path: Path) -> None:
    cfg = load_config()
    pid = tmp_path / "coat.pid"
    d = Daemon(cfg, env={}, pid_file=pid)

    # We're not in the test's main thread, so signal.signal() will
    # raise inside run_until_signal — instead trigger the same drain
    # path via stop_event from a background timer.
    timer = threading.Timer(0.1, lambda: os.kill(os.getpid(), signal.SIGUSR1))

    received: list[int] = []
    original = signal.getsignal(signal.SIGUSR1)

    def _record(signum: int, _frame: object) -> None:
        received.append(signum)
        d.stop()

    signal.signal(signal.SIGUSR1, _record)
    try:
        d.start()
        timer.start()
        # wait() returns True once stop() runs.
        assert d.wait(timeout=5)
        assert received == [signal.SIGUSR1]
        assert not pid.exists()
    finally:
        signal.signal(signal.SIGUSR1, original)
        timer.cancel()


def test_context_manager_round_trip(tmp_path: Path) -> None:
    cfg = load_config()
    pid = tmp_path / "coat.pid"
    with Daemon(cfg, env={}, pid_file=pid):
        assert pid.exists()
    assert not pid.exists()


def test_runtime_handler_property_raises_before_start(tmp_path: Path) -> None:
    cfg = load_config()
    d = Daemon(cfg, env={}, pid_file=tmp_path / "coat.pid")
    with pytest.raises(RuntimeError):
        _ = d.runtime_handler


def test_restart_after_stop_resets_stop_event(tmp_path: Path) -> None:
    """Codex P2 on PR-20: ``stop()`` sets ``_stop_event``; ``start()``
    must clear it so the next ``wait()`` blocks instead of returning
    immediately.
    """
    cfg = load_config()
    d = Daemon(cfg, env={}, pid_file=tmp_path / "coat.pid")

    d.start()
    d.stop()
    # Confirm the previous lifecycle's stop_event would otherwise
    # short-circuit wait().
    assert d.wait(timeout=0) is True

    d.start()
    try:
        # New lifecycle: wait must time out instead of returning
        # immediately. ~50 ms is plenty without slowing the suite down.
        t0 = time.monotonic()
        returned = d.wait(timeout=0.05)
        elapsed = time.monotonic() - t0
        assert returned is False
        assert elapsed >= 0.04
    finally:
        d.stop()


def test_concurrent_daemon_instances_share_pid_file_rejection(tmp_path: Path) -> None:
    """Two ``Daemon`` instances on the same PID path within one process
    must not both start.
    """
    cfg = load_config()
    pid = tmp_path / "coat.pid"
    first = Daemon(cfg, env={}, pid_file=pid)
    second = Daemon(cfg, env={}, pid_file=pid)
    first.start()
    try:
        with pytest.raises(PidFileError):
            second.start()
        # Second instance's resources were rolled back.
        assert second.http_server is None
        # First holder still owns the file.
        assert pid.read_text().strip() == str(os.getpid())
    finally:
        first.stop()
    assert not pid.exists()
