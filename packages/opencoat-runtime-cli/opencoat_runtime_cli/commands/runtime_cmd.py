"""``COATr runtime up | down | status`` over the daemon's HTTP JSON-RPC (M4 PR-21).

* ``up`` spawns ``python -m opencoat_runtime_daemon`` (double-forking when
  ``--detach`` is set so the daemon is owned by init, not the CLI),
  then polls ``health.ping`` until the HTTP listener answers or the
  wait budget expires.
* ``down`` reads the daemon's PID file and sends ``SIGTERM`` — the
  daemon's signal handler installs the same drain path as PR-20.
* ``status`` POSTs ``health.ping``; reports *running* / *stopped* and
  echoes any companion PID file.

The ``reload`` action is reserved — wiring ``Daemon.reload()`` over RPC
lands in a later PR. We surface a clean error today instead of a stub
``NotImplementedError`` traceback.
"""

from __future__ import annotations

import argparse
import contextlib
import errno
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Literal

from .._http import add_endpoint_args, make_client
from ..transport import HttpRpcCallError, HttpRpcClient, HttpRpcConnectionError, HttpRpcError

_DEFAULT_WAIT_SECONDS = 10.0
_HEALTH_POLL_INTERVAL_SECONDS = 0.1


# ----------------------------------------------------------------------
# PID file helpers
# ----------------------------------------------------------------------


def _read_pid_file(path: Path) -> int | None:
    try:
        text = path.read_text().strip()
    except FileNotFoundError:
        return None
    except OSError as exc:
        print(f"runtime: could not read {path}: {exc}", file=sys.stderr)
        return None
    try:
        pid = int(text)
    except ValueError:
        print(f"runtime: pid file {path} is not numeric: {text!r}", file=sys.stderr)
        return None
    return pid if pid > 0 else None


def _process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError as exc:
        if exc.errno == errno.ESRCH:
            return False
        return exc.errno == errno.EPERM
    return True


# ----------------------------------------------------------------------
# up
# ----------------------------------------------------------------------


def _daemon_argv(args: argparse.Namespace) -> list[str]:
    cmd: list[str] = [sys.executable, "-m", "opencoat_runtime_daemon"]
    if args.config is not None:
        cmd += ["--config", str(args.config)]
    if args.pid_file is not None:
        cmd += ["--pid-file", str(args.pid_file)]
    if args.log_level:
        cmd += ["--log-level", args.log_level]
    return cmd


def _spawn_daemon_foreground(args: argparse.Namespace) -> subprocess.Popen[bytes]:
    """Spawn the daemon attached to this process (for ``--foreground``)."""
    return subprocess.Popen(
        _daemon_argv(args),
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )


def _spawn_daemon_detached(args: argparse.Namespace) -> None:
    """Double-fork + exec the daemon so it is owned by init, not the CLI.

    POSIX daemonization pattern (cf. APUE §13). After this returns the
    daemon is *not* a child of the current process — no zombie can
    leak back if the daemon later exits while we are still alive
    (e.g. inside the test process running both ``up`` and ``down``).
    """
    if not hasattr(os, "fork"):  # pragma: no cover — POSIX-only path
        raise RuntimeError("--detach requires a POSIX platform; use --foreground")

    cmd = _daemon_argv(args)
    pid = os.fork()
    if pid > 0:
        # Original CLI parent: reap the first child immediately so we
        # don't even hold *its* zombie. The grandchild is then orphaned
        # to init.
        with contextlib.suppress(OSError):
            os.waitpid(pid, 0)
        return

    try:
        os.setsid()
        pid2 = os.fork()
        if pid2 > 0:
            os._exit(0)
        # Grandchild: redirect stdio to /dev/null so the CLI's tty does
        # not stay tied to the daemon's lifetime.
        devnull_r = os.open(os.devnull, os.O_RDONLY)
        devnull_w = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull_r, 0)
        os.dup2(devnull_w, 1)
        os.dup2(devnull_w, 2)
        if devnull_r > 2:
            os.close(devnull_r)
        if devnull_w > 2:
            os.close(devnull_w)
        os.execvp(cmd[0], cmd)
    except BaseException:
        os._exit(127)


def _wait_for_health(client: HttpRpcClient, deadline: float) -> bool:
    while time.monotonic() < deadline:
        try:
            result = client.call("health.ping")
        except HttpRpcConnectionError:
            time.sleep(_HEALTH_POLL_INTERVAL_SECONDS)
            continue
        except HttpRpcError as exc:
            print(f"runtime up: unexpected RPC error: {exc}", file=sys.stderr)
            return False
        return bool(result and result.get("ok"))
    return False


def _runtime_up(args: argparse.Namespace) -> int:
    client = make_client(args, timeout=1.5)

    probe = _probe_endpoint(client)
    if probe.state == "ours":
        print(f"runtime: already running at {client.endpoint}")
        return 0
    if probe.state == "foreign":
        # Something else is occupying the configured host:port. Refusing
        # to spawn here surfaces the port conflict instead of silently
        # exiting 0 the way the previous `_is_endpoint_dead` did
        # (Codex P1 on PR-21).
        print(
            f"runtime up: refusing to spawn — {client.endpoint} is bound by "
            f"another service ({probe.detail}). Free the port or override "
            "with --host/--port/--path.",
            file=sys.stderr,
        )
        return 1

    if args.detach and not hasattr(os, "fork"):
        # Codex P2 on PR-21: detached spawn requires POSIX fork(). On
        # platforms without it we used to traceback inside
        # `_spawn_daemon_detached` for the default invocation. Surface
        # a clean CLI error pointing the user at --foreground.
        print(
            "runtime up: --detach requires a POSIX platform (os.fork is unavailable). "
            "Re-run with --foreground to start the daemon attached to this terminal.",
            file=sys.stderr,
        )
        return 2

    proc: subprocess.Popen[bytes] | None = None
    if args.detach:
        _spawn_daemon_detached(args)
    else:
        proc = _spawn_daemon_foreground(args)

    deadline = time.monotonic() + max(0.5, float(args.wait_seconds))
    healthy = _wait_for_health(client, deadline)

    if not healthy:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)
        # When detached we cannot terminate via Popen; ask the pid file
        # owner (if any) to drain.
        if args.detach and args.pid_file is not None:
            pid = _read_pid_file(Path(args.pid_file))
            if pid is not None and _process_alive(pid):
                with contextlib.suppress(OSError):
                    os.kill(pid, signal.SIGTERM)
        print(
            f"runtime up: daemon did not become healthy within {args.wait_seconds}s",
            file=sys.stderr,
        )
        return 1

    pid_suffix = ""
    if args.pid_file is not None:
        pid = _read_pid_file(Path(args.pid_file))
        if pid is not None:
            pid_suffix = f" pid={pid}"
    print(f"runtime up: serving at {client.endpoint}{pid_suffix}")
    return 0


class _EndpointProbe:
    """Result of probing the configured host:port with ``health.ping``.

    Three terminal states:

    * ``"dead"`` — nothing answered on the socket (ECONNREFUSED /
      timeout). Safe for ``runtime up`` to spawn a fresh daemon.
    * ``"ours"`` — a OpenCOAT daemon answered the ping with ``ok=true``.
      ``runtime up`` should no-op with *already running*.
    * ``"foreign"`` — something is bound on the port but is not our
      daemon (wrong response shape, unrelated HTTP service, JSON-RPC
      server that doesn't recognise ``health.ping``). ``runtime up``
      must surface this as a hard error instead of silently exiting
      0 (Codex P1 on PR-21).
    """

    __slots__ = ("detail", "state")

    def __init__(self, state: Literal["dead", "ours", "foreign"], detail: str = "") -> None:
        self.state: Literal["dead", "ours", "foreign"] = state
        self.detail = detail


def _probe_endpoint(client: HttpRpcClient) -> _EndpointProbe:
    try:
        result = client.call("health.ping")
    except HttpRpcConnectionError:
        return _EndpointProbe("dead")
    except HttpRpcCallError as exc:
        # Some other JSON-RPC service occupies the port (or our daemon
        # is broken). Either way: not ours.
        return _EndpointProbe("foreign", f"JSON-RPC error {exc.code}: {exc.message}")
    except HttpRpcError as exc:
        # Wrong-shape HTTP response, HTML 404 from a different web app,
        # etc. — definitely not our daemon.
        return _EndpointProbe("foreign", str(exc))
    if isinstance(result, dict) and result.get("ok") is True:
        return _EndpointProbe("ours")
    return _EndpointProbe("foreign", f"unexpected health.ping result: {result!r}")


# ----------------------------------------------------------------------
# down
# ----------------------------------------------------------------------


def _runtime_down(args: argparse.Namespace) -> int:
    if args.pid_file is None:
        print("runtime down: --pid-file is required", file=sys.stderr)
        return 2
    pid_path = Path(args.pid_file)
    pid = _read_pid_file(pid_path)
    if pid is None:
        print(f"runtime: no daemon pid recorded at {pid_path} — assuming stopped")
        return 0
    if not _process_alive(pid):
        print(f"runtime: pid {pid} from {pid_path} is not alive — assuming stopped")
        return 0

    sig = signal.SIGKILL if args.force else signal.SIGTERM
    try:
        os.kill(pid, sig)
    except ProcessLookupError:
        print(f"runtime: pid {pid} already gone")
        return 0
    except PermissionError as exc:
        print(f"runtime down: not allowed to signal pid {pid}: {exc}", file=sys.stderr)
        return 1

    deadline = time.monotonic() + max(0.5, float(args.wait_seconds))
    while time.monotonic() < deadline:
        if not _process_alive(pid):
            print(f"runtime down: pid {pid} stopped")
            return 0
        time.sleep(_HEALTH_POLL_INTERVAL_SECONDS)

    print(
        f"runtime down: pid {pid} still alive after {args.wait_seconds}s (try --force for SIGKILL)",
        file=sys.stderr,
    )
    return 1


# ----------------------------------------------------------------------
# status
# ----------------------------------------------------------------------


def _runtime_status(args: argparse.Namespace) -> int:
    client = make_client(args, timeout=2.0)
    pid: int | None = None
    pid_alive: bool | None = None
    if args.pid_file is not None:
        pid = _read_pid_file(Path(args.pid_file))
        if pid is not None:
            pid_alive = _process_alive(pid)

    try:
        result = client.call("health.ping")
    except HttpRpcConnectionError:
        print(f"runtime: stopped (endpoint={client.endpoint})")
        if pid is not None:
            state = "alive" if pid_alive else "dead"
            print(f"  pid-file: {args.pid_file} pid={pid} ({state})")
        return 3
    except HttpRpcCallError as exc:
        print(
            f"runtime: degraded (endpoint={client.endpoint}, rpc-error {exc.code}: {exc.message})",
            file=sys.stderr,
        )
        return 4
    except HttpRpcError as exc:
        print(f"runtime: degraded (endpoint={client.endpoint}, {exc})", file=sys.stderr)
        return 4

    ok = bool(result and result.get("ok"))
    label = "running" if ok else "degraded"
    print(f"runtime: {label} (endpoint={client.endpoint})")
    if pid is not None:
        state = "alive" if pid_alive else "dead"
        print(f"  pid-file: {args.pid_file} pid={pid} ({state})")
    return 0 if ok else 4


# ----------------------------------------------------------------------
# reload (deferred)
# ----------------------------------------------------------------------


def _runtime_reload(_args: argparse.Namespace) -> int:
    print(
        "runtime reload: not yet exposed over HTTP — "
        "send SIGHUP to the daemon, or use `runtime down` + `runtime up`.",
        file=sys.stderr,
    )
    return 2


# ----------------------------------------------------------------------
# argparse wiring
# ----------------------------------------------------------------------


_ACTIONS = {
    "up": _runtime_up,
    "down": _runtime_down,
    "status": _runtime_status,
    "reload": _runtime_reload,
}


def _handle(args: argparse.Namespace) -> int:
    func = _ACTIONS.get(args.action)
    if func is None:  # pragma: no cover — argparse choices guards this
        print(f"runtime: unknown action {args.action!r}", file=sys.stderr)
        return 2
    return func(args)


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("runtime", help="manage the OpenCOAT Runtime daemon")
    p.add_argument(
        "action",
        choices=sorted(_ACTIONS.keys()),
        help="up | down | status | reload",
    )
    add_endpoint_args(p)
    p.add_argument(
        "--pid-file",
        type=Path,
        default=None,
        help="PID file path; required by `down`, optional for `up`/`status`.",
    )
    p.add_argument(
        "--wait-seconds",
        type=float,
        default=_DEFAULT_WAIT_SECONDS,
        help="how long to wait for the daemon to become healthy / drain (seconds).",
    )
    p.add_argument(
        "--log-level",
        default="INFO",
        help="log level passed through to the spawned daemon on `up`.",
    )
    detach = p.add_mutually_exclusive_group()
    detach.add_argument(
        "--detach",
        dest="detach",
        action="store_true",
        default=True,
        help="`up` runs the daemon in a new session (default).",
    )
    detach.add_argument(
        "--foreground",
        dest="detach",
        action="store_false",
        help="`up` keeps the daemon attached to this terminal.",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="`down`: send SIGKILL instead of SIGTERM.",
    )
    p.set_defaults(func=_handle)


__all__ = ["register"]
