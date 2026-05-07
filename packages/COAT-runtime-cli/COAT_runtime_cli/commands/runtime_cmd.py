"""COATr runtime up | down | status | reload."""

from __future__ import annotations

import argparse


def _handle(args: argparse.Namespace) -> int:
    raise NotImplementedError(f"COATr runtime {args.action} arrives at M4")


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("runtime", help="manage the COAT Runtime daemon")
    p.add_argument("action", choices=["up", "down", "status", "reload"])
    p.set_defaults(func=_handle)
