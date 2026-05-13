"""PID-file helper (M4 PR-20).

Used by :class:`~opencoat_runtime_daemon.daemon.Daemon` to advertise the
running daemon's PID and to refuse to start a second daemon over a live
one. Stale files (process gone) are replaced atomically.
"""

from __future__ import annotations

import contextlib
import errno
import os
from pathlib import Path


class PidFileError(RuntimeError):
    """Raised when a PID file already points at a *live* process."""


def _read_pid(path: Path) -> int | None:
    try:
        text = path.read_text().strip()
    except FileNotFoundError:
        return None
    except OSError:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _process_alive(pid: int) -> bool:
    """Return True iff ``pid`` looks live on this host (POSIX only).

    Sends signal 0 — that's a no-op delivery that only succeeds for a
    live process the caller can address. ESRCH → gone, EPERM → alive
    but not ours (still alive).
    """
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError as exc:
        if exc.errno == errno.ESRCH:
            return False
        # EPERM means it exists but isn't ours — still alive.
        return exc.errno == errno.EPERM
    return True


class PidFile:
    """Context manager that owns a PID file for the current process.

    On ``__enter__`` the file is created exclusively (``O_EXCL``). If it
    already exists but the recorded PID is dead, the stale file is
    removed and a fresh one written. If the existing PID is still
    alive, :class:`PidFileError` is raised — *including* when the
    existing PID is **our own**, because in that case another
    ``PidFile``/``Daemon`` instance in this process already owns the
    path (Codex P2 on PR-20).

    On ``__exit__`` (or explicit :meth:`release`) the file is removed
    *only* if it still contains our PID — protecting against races
    where another daemon adopted the path between our writes.
    """

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self._path = Path(path)
        self._owned = False

    @property
    def path(self) -> Path:
        return self._path

    def acquire(self) -> None:
        if self._owned:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        my_pid = os.getpid()
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        try:
            fd = os.open(self._path, flags, 0o644)
        except FileExistsError:
            existing = _read_pid(self._path)
            # Treat our own PID as a live owner: another PidFile in
            # this process already holds the path. _process_alive
            # would return True for my_pid too, but we spell the
            # check out for clarity and a better error message.
            if existing is not None and (existing == my_pid or _process_alive(existing)):
                owner = "this process" if existing == my_pid else f"live PID {existing}"
                raise PidFileError(f"PID file {self._path} already owned by {owner}") from None
            # Stale (dead PID or unreadable file) — replace it.
            with contextlib.suppress(FileNotFoundError):
                self._path.unlink()
            fd = os.open(self._path, flags, 0o644)
        try:
            os.write(fd, f"{my_pid}\n".encode())
        finally:
            os.close(fd)
        self._owned = True

    def release(self) -> None:
        if not self._owned:
            return
        self._owned = False
        existing = _read_pid(self._path)
        if existing != os.getpid():
            # Someone else owns it now — leave it alone.
            return
        try:
            self._path.unlink()
        except FileNotFoundError:
            return

    def __enter__(self) -> PidFile:
        self.acquire()
        return self

    def __exit__(self, *exc: object) -> None:
        self.release()


__all__ = ["PidFile", "PidFileError"]
