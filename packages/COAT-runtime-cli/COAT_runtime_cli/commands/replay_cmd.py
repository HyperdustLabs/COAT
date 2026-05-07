"""COATr replay <session.jsonl>."""

from __future__ import annotations

import argparse


def _handle(args: argparse.Namespace) -> int:
    raise NotImplementedError("COATr replay arrives at M3")


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("replay", help="replay a recorded session")
    p.add_argument("path", help="path to a session.jsonl produced by the jsonl backend")
    p.set_defaults(func=_handle)
