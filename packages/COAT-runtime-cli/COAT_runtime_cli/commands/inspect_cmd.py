"""COATr inspect joinpoints | pointcuts."""

from __future__ import annotations

import argparse


def _handle(args: argparse.Namespace) -> int:
    if args.what == "joinpoints":
        from COAT_runtime_core.joinpoint import JOINPOINT_CATALOG

        for entry in JOINPOINT_CATALOG:
            print(f"{entry.level.label:<16} {entry.name}")
        return 0
    raise NotImplementedError(f"COATr inspect {args.what} arrives at M4")


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("inspect", help="introspect runtime tables")
    p.add_argument("what", choices=["joinpoints", "pointcuts"])
    p.set_defaults(func=_handle)
