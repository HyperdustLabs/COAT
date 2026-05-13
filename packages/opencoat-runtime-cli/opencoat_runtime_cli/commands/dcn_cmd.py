"""``opencoat dcn export | visualize | activation-log | import`` (M4 PR-22).

The DCN port doesn't (yet) expose a clean enumerate-everything API —
nodes / edges are accessible only via private attributes on the
``MemoryDCNStore``. Until a future PR lands ``dcn.snapshot`` over RPC
we ship the *shallow* snapshot the existing JSON-RPC surface can give
us: the concern list plus the activation history. That's enough to
drive visualisation (which joinpoints fire which concerns?) and is
honest about its limitations.

``import`` is reserved — it needs a write API on ``DCNStore`` that we
haven't designed yet. We emit a clean CLI error today rather than a
stub traceback.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .._http import add_endpoint_args, make_client
from ..transport import HttpRpcCallError, HttpRpcConnectionError, HttpRpcError
from ..visualize.dcn_dot import dcn_to_dot


def _emit_rpc_error(prefix: str, exc: HttpRpcError) -> int:
    if isinstance(exc, HttpRpcConnectionError):
        print(f"{prefix}: daemon not reachable: {exc}", file=sys.stderr)
        return 3
    if isinstance(exc, HttpRpcCallError):
        print(f"{prefix}: {exc.message} (code {exc.code})", file=sys.stderr)
        return 4
    print(f"{prefix}: {exc}", file=sys.stderr)
    return 4


def _fetch_snapshot(args: argparse.Namespace) -> dict[str, Any] | int:
    """Pull concerns + activation log from the daemon. Returns an exit
    code on error, the snapshot dict on success."""
    client = make_client(args)
    try:
        concerns = client.call("concern.list", {})
        log_params: dict[str, Any] = {}
        if args.concern_id is not None:
            log_params["concern_id"] = args.concern_id
        if args.limit is not None:
            log_params["limit"] = int(args.limit)
        activation_log = client.call("dcn.activation_log", log_params)
    except HttpRpcError as exc:
        return _emit_rpc_error("dcn export", exc)
    return {
        "concerns": concerns if isinstance(concerns, list) else [],
        "activation_log": activation_log if isinstance(activation_log, list) else [],
    }


# ----------------------------------------------------------------------
# activation-log
# ----------------------------------------------------------------------


def _dcn_activation_log(args: argparse.Namespace) -> int:
    client = make_client(args)
    params: dict[str, Any] = {}
    if args.concern_id is not None:
        params["concern_id"] = args.concern_id
    if args.limit is not None:
        params["limit"] = int(args.limit)
    try:
        rows = client.call("dcn.activation_log", params)
    except HttpRpcError as exc:
        return _emit_rpc_error("dcn activation-log", exc)
    if not isinstance(rows, list):
        print(f"dcn activation-log: unexpected response shape: {rows!r}", file=sys.stderr)
        return 4
    if args.json:
        sys.stdout.write(json.dumps(rows, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
        return 0
    if not rows:
        print("(no activations)")
        return 0
    for row in rows:
        ts = row.get("ts", "?")
        cid = row.get("concern_id", "?")
        jp = row.get("joinpoint_id", "?")
        score = row.get("score", "?")
        print(f"{ts}  {cid:<20}  {jp:<28}  score={score}")
    return 0


# ----------------------------------------------------------------------
# export / visualize
# ----------------------------------------------------------------------


def _emit_output(text: str, output: str | None) -> None:
    if output is None or output == "-":
        sys.stdout.write(text if text.endswith("\n") else text + "\n")
        return
    Path(output).write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")


def _dcn_export(args: argparse.Namespace) -> int:
    snap = _fetch_snapshot(args)
    if isinstance(snap, int):
        return snap
    fmt = (args.format or "json").lower()
    if fmt == "json":
        body = json.dumps(snap, indent=2, sort_keys=True, ensure_ascii=False)
    elif fmt == "dot":
        body = dcn_to_dot(snap)
    else:
        print(f"dcn export: unsupported --format {fmt!r}", file=sys.stderr)
        return 2
    _emit_output(body, args.output)
    if args.output and args.output != "-":
        print(
            f"dcn export: wrote {len(snap.get('concerns', []))} concern(s) and "
            f"{len(snap.get('activation_log', []))} activation(s) → {args.output}",
            file=sys.stderr,
        )
    return 0


def _dcn_visualize(args: argparse.Namespace) -> int:
    # `visualize` is just `export --format dot` with a friendlier name.
    args.format = "dot"
    return _dcn_export(args)


# ----------------------------------------------------------------------
# import (deferred)
# ----------------------------------------------------------------------


def _dcn_import(_args: argparse.Namespace) -> int:
    print(
        "dcn import: not yet implemented — needs a write API on DCNStore (planned for M5+). "
        "Use `opencoat concern import` to load concerns; activation history is record-only.",
        file=sys.stderr,
    )
    return 2


# ----------------------------------------------------------------------
# argparse wiring
# ----------------------------------------------------------------------


_ACTIONS = {
    "export": _dcn_export,
    "visualize": _dcn_visualize,
    "activation-log": _dcn_activation_log,
    "import": _dcn_import,
}


def _handle(args: argparse.Namespace) -> int:
    func = _ACTIONS.get(args.action)
    if func is None:  # pragma: no cover — argparse choices guards this
        print(f"dcn: unknown action {args.action!r}", file=sys.stderr)
        return 2
    return func(args)


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("dcn", help="inspect / export the Deep Concern Network")
    p.add_argument("action", choices=sorted(_ACTIONS.keys()))
    add_endpoint_args(p)
    p.add_argument(
        "--format",
        default="json",
        choices=("json", "dot"),
        help="`export`: output format (default: json).",
    )
    p.add_argument(
        "-o",
        "--output",
        default=None,
        help="`export`/`visualize`: write to PATH instead of stdout (use `-` for stdout).",
    )
    p.add_argument(
        "--concern-id",
        dest="concern_id",
        default=None,
        help="`activation-log`/`export`: filter activations to this concern only.",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="`activation-log`/`export`: cap the number of activation rows.",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="`activation-log`: emit raw JSON instead of human columns.",
    )
    p.set_defaults(func=_handle)


__all__ = ["register"]
