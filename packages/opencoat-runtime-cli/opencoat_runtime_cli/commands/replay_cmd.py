"""COATr replay <session.jsonl>."""

from __future__ import annotations

import argparse
import json
import sys

from opencoat_runtime_storage.jsonl import replay_session_file


def _handle(args: argparse.Namespace) -> int:
    try:
        result = replay_session_file(args.path)
    except OSError as e:
        print(f"replay: {e}", file=sys.stderr)
        return 2
    except (ValueError, json.JSONDecodeError) as e:
        print(f"replay: {e}", file=sys.stderr)
        return 2

    print(f"replay: {result.turns} turn(s), {len(result.mismatches)} mismatch(es)")
    for m in result.mismatches:
        print(
            f"  turn {m.turn_index} joinpoint={m.joinpoint_id!r}: {m.detail}",
            file=sys.stderr,
        )
        if args.verbose:
            print("    expected:", json.dumps(m.expected, indent=2), file=sys.stderr)
            print("    actual:  ", json.dumps(m.actual, indent=2), file=sys.stderr)
    return 0 if result.ok else 1


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("replay", help="replay a recorded session (M3 JSONL)")
    p.add_argument("path", help="path to a session.jsonl produced by SessionJsonlRecorder")
    p.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="print expected vs actual injection JSON for each mismatch",
    )
    p.set_defaults(func=_handle)
