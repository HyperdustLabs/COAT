"""Top-level COATr dispatcher.

Subcommand modules under :mod:`.commands` register themselves here. M0 wires
``runtime``, ``concern``, ``dcn``, ``replay``, ``inspect``, ``plugin`` as
no-op stubs so ``COATr <cmd> --help`` works end-to-end.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable

from . import __version__
from .commands import concern_cmd, dcn_cmd, inspect_cmd, plugin_cmd, replay_cmd, runtime_cmd

CommandRegistrar = Callable[[argparse._SubParsersAction], None]
COMMANDS: tuple[CommandRegistrar, ...] = (
    runtime_cmd.register,
    concern_cmd.register,
    dcn_cmd.register,
    replay_cmd.register,
    inspect_cmd.register,
    plugin_cmd.register,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="COATr", description="COAT Runtime CLI")
    parser.add_argument("--version", action="version", version=f"COATr {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    for register in COMMANDS:
        register(sub)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "func", None)
    if handler is None:
        parser.print_help()
        return 2
    return int(handler(args) or 0)
