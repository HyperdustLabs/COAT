"""COATr plugin list | install | disable."""

from __future__ import annotations

import argparse


def _handle(args: argparse.Namespace) -> int:
    raise NotImplementedError(f"COATr plugin {args.action} arrives at M4")


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("plugin", help="manage host / matcher / advisor plugins")
    p.add_argument("action", choices=["list", "install", "disable"])
    p.add_argument("name", nargs="?")
    p.set_defaults(func=_handle)
