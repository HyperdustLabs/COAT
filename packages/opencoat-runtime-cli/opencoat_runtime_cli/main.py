"""Top-level COATr dispatcher.

Subcommand modules under :mod:`.commands` register themselves here. M0 wires
``runtime``, ``concern``, ``dcn``, ``replay``, ``inspect``, ``plugin`` as
no-op stubs so ``COATr <cmd> --help`` works end-to-end.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable
from types import SimpleNamespace

from . import __version__
from .commands import concern_cmd, dcn_cmd, inspect_cmd, plugin_cmd, replay_cmd, runtime_cmd

# Rendered once with ``pyfiglet -f big OpenCOAT`` (author-time only — no
# runtime dependency on pyfiglet).
_BANNER = (
    "  ____                    _____ ____       _______ \n"
    " / __ \\                  / ____/ __ \\   /\\|__   __|\n"
    "| |  | |_ __   ___ _ __ | |   | |  | | /  \\  | |   \n"
    "| |  | | '_ \\ / _ \\ '_ \\| |   | |  | |/ /\\ \\ | |   \n"
    "| |__| | |_) |  __/ | | | |___| |__| / ____ \\| |   \n"
    " \\____/| .__/ \\___|_| |_|\\_____\\____/_/    \\_\\_|   \n"
    "       | |                                         \n"
    "       |_|                                         "
)

_SUBTITLE = "Open Concern-Oriented Agent Thinking · COATr v{ver}"

CommandRegistrar = Callable[[argparse._SubParsersAction], None]
COMMANDS: tuple[CommandRegistrar, ...] = (
    runtime_cmd.register,
    concern_cmd.register,
    dcn_cmd.register,
    replay_cmd.register,
    inspect_cmd.register,
    plugin_cmd.register,
)


def _strip_no_banner_flag(argv: list[str]) -> tuple[list[str], bool]:
    """Pre-parse strip of the global ``--no-banner`` flag.

    Accepted anywhere *before* the POSIX end-of-options marker ``--``;
    once ``--`` is seen the rest of ``argv`` is forwarded untouched so
    a subcommand can legitimately receive a literal token named
    ``--no-banner`` (e.g. ``COATr replay -- --no-banner``).
    """
    out: list[str] = []
    no_banner = False
    it = iter(argv)
    for word in it:
        if word == "--":
            out.append(word)
            out.extend(it)
            break
        if word == "--no-banner":
            no_banner = True
            continue
        out.append(word)
    return out, no_banner


def _should_render_banner(stream, *, no_banner: bool) -> bool:
    return not no_banner and os.environ.get("NO_COLOR") is None and stream.isatty()


def _daemon_status_line() -> str:
    """One-line summary: default HTTP endpoint + ``health.ping`` outcome."""
    from opencoat_runtime_cli._http import resolve_endpoint
    from opencoat_runtime_cli.transport import (
        HttpRpcCallError,
        HttpRpcClient,
        HttpRpcConnectionError,
        HttpRpcError,
    )

    ns = SimpleNamespace(host=None, port=None, path=None, config=None)
    host, port, path = resolve_endpoint(ns)
    client = HttpRpcClient(host=host, port=port, path=path, timeout=0.4)
    try:
        result = client.call("health.ping")
    except HttpRpcConnectionError:
        status = "stopped"
    except HttpRpcCallError as exc:
        status = f"rpc_error ({exc.code})"
    except HttpRpcError as exc:
        status = f"protocol_error ({exc})"
    else:
        if isinstance(result, dict) and result.get("ok") is True:
            status = "healthy"
        else:
            status = "unknown_response"
    return f"M4 daemon: {client.endpoint}  (status: {status})"


def _profile_and_host_plugins_line() -> str:
    profile = os.environ.get("OPENCOAT_PROFILE") or "default"
    try:
        from opencoat_runtime_daemon.config import load_config

        hosts = load_config(None).plugins.hosts
    except Exception:
        return f"profile: {profile} · host plugins: — (unavailable)"
    marks = "—" if not hosts else ", ".join(hosts)
    return f"profile: {profile} · host plugins: {marks}"


def _render_banner(stream) -> None:
    stream.write(f"\n{_BANNER}\n{_SUBTITLE.format(ver=__version__)}\n")
    stream.write(f"{_daemon_status_line()}\n")
    stream.write(f"{_profile_and_host_plugins_line()}\n\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="COATr",
        description="OpenCOAT Runtime CLI (COATr).",
        epilog="Global: pass --no-banner anywhere to suppress the startup banner.",
    )
    parser.add_argument("--version", action="version", version=f"COATr {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    for register in COMMANDS:
        register(sub)
    return parser


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    raw, no_banner = _strip_no_banner_flag(raw)
    parser = build_parser()
    args = parser.parse_args(raw)
    handler = getattr(args, "func", None)
    if handler is None:
        parser.print_help()
        return 2
    if _should_render_banner(sys.stdout, no_banner=no_banner):
        _render_banner(sys.stdout)
    return int(handler(args) or 0)
