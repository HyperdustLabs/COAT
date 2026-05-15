"""Shared HTTP endpoint resolution for ``opencoat`` subcommands (M4 PR-22).

All daemon-facing subcommands (``runtime``, ``concern``, ``dcn``,
``inspect``) accept the same four endpoint flags:

* ``--host`` / ``--port`` / ``--path`` — direct overrides.
* ``--config`` — falls back to whatever ``ipc.http`` the daemon would
  bind for that config.

Without any of those flags we use the loopback default that matches
``opencoat_runtime_daemon.config.default.yaml``.

The implementation deliberately lives outside ``commands/runtime_cmd.py``
so other subcommands do not have to import the daemon-spawn machinery
to get an HTTP client.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .transport import HttpRpcClient

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 7878
_DEFAULT_PATH = "/rpc"


def add_endpoint_args(parser: argparse.ArgumentParser) -> None:
    """Attach the standard `--config / --host / --port / --path` flags."""
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="daemon config YAML (used to discover the HTTP endpoint).",
    )
    parser.add_argument(
        "--host",
        default=None,
        help=f"HTTP host override (default: from --config or {_DEFAULT_HOST}).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help=f"HTTP port override (default: from --config or {_DEFAULT_PORT}).",
    )
    parser.add_argument(
        "--path",
        default=None,
        help=f"HTTP path override (default: from --config or {_DEFAULT_PATH}).",
    )


def resolve_endpoint(args: argparse.Namespace) -> tuple[str, int, str]:
    """Resolve ``(host, port, path)`` from CLI args → config → defaults."""
    from opencoat_runtime_daemon.config.loader import resolve_daemon_config_path

    host = getattr(args, "host", None)
    port = getattr(args, "port", None)
    path = getattr(args, "path", None)

    cfg_path = resolve_daemon_config_path(getattr(args, "config", None))
    if (host is None or port is None or path is None) and cfg_path is not None:
        try:
            from opencoat_runtime_daemon.config import load_config  # type: ignore[import-not-found]

            cfg = load_config(Path(cfg_path))
            ipc = cfg.ipc.http
            if host is None:
                host = getattr(ipc, "host", _DEFAULT_HOST) or _DEFAULT_HOST
            if port is None:
                port = int(getattr(ipc, "port", _DEFAULT_PORT) or _DEFAULT_PORT)
            if path is None:
                path = getattr(ipc, "path", _DEFAULT_PATH) or _DEFAULT_PATH
        except Exception as exc:  # pragma: no cover — surfaced via --host/--port
            print(f"runtime: warning — could not read config {cfg_path}: {exc}", file=sys.stderr)

    return (
        host or _DEFAULT_HOST,
        int(port if port is not None else _DEFAULT_PORT),
        path or _DEFAULT_PATH,
    )


def make_client(args: argparse.Namespace, *, timeout: float = 5.0) -> HttpRpcClient:
    host, port, path = resolve_endpoint(args)
    return HttpRpcClient(host=host, port=port, path=path, timeout=timeout)


__all__ = [
    "add_endpoint_args",
    "make_client",
    "resolve_endpoint",
]
