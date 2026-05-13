"""Top-level opencoat dispatcher.

Subcommand modules under :mod:`.commands` register themselves here. M0 wires
``runtime``, ``configure``, ``concern``, ``dcn``, ``replay``, ``inspect``, ``plugin`` as
no-op stubs so ``opencoat <cmd> --help`` works end-to-end.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

from . import __version__
from .commands import (
    concern_cmd,
    configure_cmd,
    dcn_cmd,
    demo_cmd,
    inspect_cmd,
    plugin_cmd,
    replay_cmd,
    runtime_cmd,
)

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

_SUBTITLE = "Open Concern-Oriented Agent Thinking · opencoat v{ver}"

CommandRegistrar = Callable[[argparse._SubParsersAction], None]
COMMANDS: tuple[CommandRegistrar, ...] = (
    runtime_cmd.register,
    configure_cmd.register,
    concern_cmd.register,
    dcn_cmd.register,
    replay_cmd.register,
    inspect_cmd.register,
    plugin_cmd.register,
    demo_cmd.register,
)


def _strip_no_banner_flag(argv: list[str]) -> tuple[list[str], bool]:
    """Pre-parse strip of the global ``--no-banner`` flag.

    Accepted anywhere *before* the POSIX end-of-options marker ``--``;
    once ``--`` is seen the rest of ``argv`` is forwarded untouched so
    a subcommand can legitimately receive a literal token named
    ``--no-banner`` (e.g. ``opencoat replay -- --no-banner``).
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
    """One-line summary: default HTTP endpoint + ``health.ping`` outcome + LLM kind.

    When the daemon is up we also probe ``runtime.llm_info`` so a stub-
    fallback shows up in the very first banner the operator sees,
    instead of being a mystery several commands later. The probe is
    best-effort: an older daemon predating that RPC (or a transient
    error) just elides the ``llm: …`` suffix.
    """
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
    llm_suffix = ""
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
            llm_suffix = _daemon_llm_suffix(client)
        else:
            status = "unknown_response"
    return f"M4 daemon: {client.endpoint}  (status: {status}{llm_suffix})"


def _daemon_llm_suffix(client: Any) -> str:
    """Build the ``, llm: …`` suffix from a probe of ``runtime.llm_info``.

    Always returns a string starting with ``", "`` (or empty when the
    probe fails). Centralised here so the banner can stay one-line.

    ``client`` is typed as :class:`~typing.Any` because the banner
    code uses a real :class:`HttpRpcClient` in production but the
    banner test injects a small duck-typed double so the suite
    doesn't need a live HTTP server just to exercise the
    "old daemon, no ``runtime.llm_info``" path.
    """
    from opencoat_runtime_cli.transport import HttpRpcError

    try:
        info = client.call("runtime.llm_info", {})
    except HttpRpcError:
        return ""
    if not isinstance(info, dict):
        return ""
    label = str(info.get("label") or "?")
    if info.get("real") is False:
        # Surface stub / stub-fallback with a visual warn so the
        # operator can't miss it even under banner clutter.
        return f", llm: {label} (degraded — no real provider wired)"
    return f", llm: {label}"


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
        prog="opencoat",
        description="OpenCOAT Runtime CLI.",
        epilog="Global: pass --no-banner anywhere to suppress the startup banner.",
    )
    parser.add_argument("--version", action="version", version=f"opencoat {__version__}")
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
