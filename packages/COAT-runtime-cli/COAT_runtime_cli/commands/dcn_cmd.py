"""COATr dcn export | import | visualize."""

from __future__ import annotations

import argparse


def _handle(args: argparse.Namespace) -> int:
    raise NotImplementedError(f"COATr dcn {args.action} arrives at M4")


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("dcn", help="inspect / export the Deep Concern Network")
    p.add_argument("action", choices=["export", "import", "visualize"])
    p.add_argument("--format", default="json")
    p.set_defaults(func=_handle)
