"""COATr concern list | show | diff | import | export."""

from __future__ import annotations

import argparse


def _handle(args: argparse.Namespace) -> int:
    raise NotImplementedError(f"COATr concern {args.action} arrives at M4")


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("concern", help="inspect and manage Concerns")
    p.add_argument("action", choices=["list", "show", "diff", "import", "export"])
    p.add_argument("target", nargs="?")
    p.set_defaults(func=_handle)
