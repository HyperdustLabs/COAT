"""Tests for :class:`~COAT_runtime_daemon._pidfile.PidFile` (M4 PR-20)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from COAT_runtime_daemon._pidfile import PidFile, PidFileError


def test_acquire_writes_our_pid(tmp_path: Path) -> None:
    pf = PidFile(tmp_path / "coat.pid")
    pf.acquire()
    try:
        assert pf.path.read_text().strip() == str(os.getpid())
    finally:
        pf.release()


def test_release_removes_only_when_we_own_it(tmp_path: Path) -> None:
    p = tmp_path / "coat.pid"
    pf = PidFile(p)
    pf.acquire()
    pf.release()
    assert not p.exists()


def test_release_keeps_file_if_owned_by_other_pid(tmp_path: Path) -> None:
    p = tmp_path / "coat.pid"
    pf = PidFile(p)
    pf.acquire()
    # Simulate another daemon adopting the path before we release.
    p.write_text("99999999\n")
    pf.release()
    assert p.exists()
    assert p.read_text().strip() == "99999999"


def test_acquire_replaces_stale_pid(tmp_path: Path) -> None:
    p = tmp_path / "coat.pid"
    # A dead PID — write something almost certainly not a live process.
    p.write_text("2147483646\n")
    pf = PidFile(p)
    pf.acquire()
    try:
        assert p.read_text().strip() == str(os.getpid())
    finally:
        pf.release()


def test_acquire_rejects_live_pid(tmp_path: Path) -> None:
    p = tmp_path / "coat.pid"
    # PID 1 (init) is always alive on POSIX.
    p.write_text("1\n")
    pf = PidFile(p)
    with pytest.raises(PidFileError):
        pf.acquire()


def test_acquire_is_idempotent(tmp_path: Path) -> None:
    pf = PidFile(tmp_path / "coat.pid")
    pf.acquire()
    try:
        pf.acquire()  # should not raise
        assert pf.path.read_text().strip() == str(os.getpid())
    finally:
        pf.release()


def test_context_manager_round_trip(tmp_path: Path) -> None:
    p = tmp_path / "coat.pid"
    with PidFile(p):
        assert p.exists()
    assert not p.exists()


def test_acquire_creates_parent_dirs(tmp_path: Path) -> None:
    p = tmp_path / "nested" / "run" / "coat.pid"
    with PidFile(p):
        assert p.exists()
    assert not p.exists()
