"""``opencoat concern list | show | import | export | diff`` (M4 PR-22).

All actions reach the daemon over the HTTP JSON-RPC client introduced
in PR-21. The wire methods are ``concern.list``, ``concern.get``, and
``concern.upsert`` — no extra server-side work was required for this
PR.

Defaults are tuned for human terminals: ``list`` prints
``<id>  <state>  <name>`` columns; ``--json`` switches to a single
JSON array suitable for piping into ``jq`` or another ``opencoat concern
import``.
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path
from typing import Any

import yaml

from .._http import add_endpoint_args, make_client
from ..transport import (
    HttpRpcCallError,
    HttpRpcConnectionError,
    HttpRpcError,
)

# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------


def _emit_rpc_error(prefix: str, exc: HttpRpcError) -> int:
    """Map transport / RPC errors onto stable CLI exit codes."""
    if isinstance(exc, HttpRpcConnectionError):
        print(f"{prefix}: daemon not reachable: {exc}", file=sys.stderr)
        return 3
    if isinstance(exc, HttpRpcCallError):
        print(f"{prefix}: {exc.message} (code {exc.code})", file=sys.stderr)
        return 4
    print(f"{prefix}: {exc}", file=sys.stderr)
    return 4


def _load_concerns_file(path: Path) -> list[dict[str, Any]]:
    """Parse a JSON or YAML file containing one or many concerns.

    YAML covers the human-authored input case; JSON is the canonical
    output of ``concern export``. We accept either a single mapping or
    a list of mappings.
    """
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    data = yaml.safe_load(text) if suffix in {".yaml", ".yml"} else json.loads(text)
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                raise ValueError(f"{path}: list entries must be objects, got {type(item).__name__}")
        return data
    raise ValueError(f"{path}: top-level must be an object or a list of objects")


def _pretty(obj: Any) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False)


# ----------------------------------------------------------------------
# list
# ----------------------------------------------------------------------


def _concern_list(args: argparse.Namespace) -> int:
    params: dict[str, Any] = {}
    for src, dst in (
        ("kind", "kind"),
        ("tag", "tag"),
        ("lifecycle_state", "lifecycle_state"),
        ("limit", "limit"),
    ):
        v = getattr(args, src, None)
        if v is not None:
            params[dst] = v

    client = make_client(args)
    try:
        rows = client.call("concern.list", params)
    except HttpRpcError as exc:
        return _emit_rpc_error("concern list", exc)

    if not isinstance(rows, list):
        print(f"concern list: unexpected response shape: {rows!r}", file=sys.stderr)
        return 4

    if args.json:
        sys.stdout.write(_pretty(rows) + "\n")
        return 0

    if not rows:
        print("(no concerns)")
        return 0
    for c in rows:
        cid = c.get("id", "?")
        state = c.get("lifecycle_state", "?")
        name = c.get("name", "")
        print(f"{cid}  {state:<10}  {name}")
    return 0


# ----------------------------------------------------------------------
# show
# ----------------------------------------------------------------------


def _concern_show(args: argparse.Namespace) -> int:
    if not args.target:
        print("concern show: <concern_id> is required", file=sys.stderr)
        return 2
    client = make_client(args)
    try:
        c = client.call("concern.get", {"concern_id": args.target})
    except HttpRpcError as exc:
        return _emit_rpc_error("concern show", exc)
    if c is None:
        print(f"concern show: no concern with id {args.target!r}", file=sys.stderr)
        return 1
    sys.stdout.write(_pretty(c) + "\n")
    return 0


# ----------------------------------------------------------------------
# import
# ----------------------------------------------------------------------


def _concern_import(args: argparse.Namespace) -> int:
    use_demo = bool(getattr(args, "demo", False))
    if use_demo and args.target:
        print(
            "concern import: --demo is mutually exclusive with <path>",
            file=sys.stderr,
        )
        return 2
    if not use_demo and not args.target:
        print("concern import: <path> is required (or pass --demo)", file=sys.stderr)
        return 2

    if use_demo:
        # In-tree demo set: produce JSON-mode dicts so the daemon's
        # ``concern.upsert`` parser handles them identically to a file
        # import. ``model_dump(mode="json")`` collapses enums to their
        # string values and datetimes to ISO strings.
        from ..demo_concerns import demo_concerns

        concerns = [c.model_dump(mode="json", exclude_none=True) for c in demo_concerns()]
        source_label = "--demo set"
    else:
        path = Path(args.target)
        try:
            concerns = _load_concerns_file(path)
        except (OSError, ValueError, json.JSONDecodeError, yaml.YAMLError) as exc:
            print(f"concern import: {exc}", file=sys.stderr)
            return 2
        source_label = str(path)

    client = make_client(args)
    imported: list[str] = []
    for raw in concerns:
        try:
            out = client.call("concern.upsert", {"concern": raw})
        except HttpRpcError as exc:
            return _emit_rpc_error("concern import", exc)
        if isinstance(out, dict):
            cid = out.get("id") or raw.get("id") or "?"
            imported.append(str(cid))
    print(f"concern import: upserted {len(imported)} concern(s) from {source_label}")
    for cid in imported:
        print(f"  {cid}")
    return 0


# ----------------------------------------------------------------------
# export
# ----------------------------------------------------------------------


def _concern_export(args: argparse.Namespace) -> int:
    client = make_client(args)
    payload: Any
    try:
        if args.target:
            c = client.call("concern.get", {"concern_id": args.target})
            if c is None:
                print(f"concern export: no concern with id {args.target!r}", file=sys.stderr)
                return 1
            payload = [c]
        else:
            payload = client.call("concern.list", {})
    except HttpRpcError as exc:
        return _emit_rpc_error("concern export", exc)

    text = _pretty(payload) + "\n"
    if args.output is None:
        sys.stdout.write(text)
    else:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"concern export: wrote {len(payload)} concern(s) → {args.output}")
    return 0


# ----------------------------------------------------------------------
# diff
# ----------------------------------------------------------------------


def _concern_diff(args: argparse.Namespace) -> int:
    if not args.target or not args.target_b:
        print("concern diff: <a> <b> are required", file=sys.stderr)
        return 2
    client = make_client(args)
    try:
        a = client.call("concern.get", {"concern_id": args.target})
        b = client.call("concern.get", {"concern_id": args.target_b})
    except HttpRpcError as exc:
        return _emit_rpc_error("concern diff", exc)
    missing = [t for t, v in ((args.target, a), (args.target_b, b)) if v is None]
    if missing:
        print(f"concern diff: missing concern(s): {', '.join(missing)}", file=sys.stderr)
        return 1
    left = _pretty(a).splitlines(keepends=True)
    right = _pretty(b).splitlines(keepends=True)
    diff = difflib.unified_diff(left, right, fromfile=args.target, tofile=args.target_b, n=3)
    text = "".join(diff)
    if not text:
        print(f"(no diff between {args.target} and {args.target_b})")
        return 0
    sys.stdout.write(text)
    return 0


# ----------------------------------------------------------------------
# argparse wiring
# ----------------------------------------------------------------------


_ACTIONS = {
    "list": _concern_list,
    "show": _concern_show,
    "import": _concern_import,
    "export": _concern_export,
    "diff": _concern_diff,
}


def _handle(args: argparse.Namespace) -> int:
    func = _ACTIONS.get(args.action)
    if func is None:  # pragma: no cover — argparse choices guards this
        print(f"concern: unknown action {args.action!r}", file=sys.stderr)
        return 2
    return func(args)


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("concern", help="inspect and manage Concerns")
    p.add_argument("action", choices=sorted(_ACTIONS.keys()))
    p.add_argument(
        "target",
        nargs="?",
        help="concern id for `show` / `diff` / `export`, file path for `import`.",
    )
    p.add_argument(
        "target_b",
        nargs="?",
        help="second concern id for `diff`.",
    )
    add_endpoint_args(p)
    p.add_argument(
        "--kind",
        default=None,
        help="`list`: filter by concern kind.",
    )
    p.add_argument(
        "--tag",
        default=None,
        help="`list`: filter by tag.",
    )
    p.add_argument(
        "--lifecycle-state",
        dest="lifecycle_state",
        default=None,
        help="`list`: filter by lifecycle state (active / weakened / archived / candidate).",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="`list`: cap the number of rows returned.",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="`list`: emit the raw JSON array instead of human columns.",
    )
    p.add_argument(
        "-o",
        "--output",
        default=None,
        help="`export`: write to this file instead of stdout.",
    )
    p.add_argument(
        "--demo",
        action="store_true",
        help=(
            "`import`: load the in-tree demo set "
            "(demo-prompt-prefix / demo-tool-block / demo-memory-tag) "
            "instead of reading a file."
        ),
    )
    p.set_defaults(func=_handle)


__all__ = ["register"]
