"""``opencoat inspect joinpoints | pointcuts`` (M0 baseline + M4 PR-22).

Both targets are read-only catalogs that live inside
:mod:`opencoat_runtime_core` — they don't depend on a running daemon. We
read them directly so ``opencoat inspect`` works offline.
"""

from __future__ import annotations

import argparse
import sys

from opencoat_runtime_core.joinpoint import JOINPOINT_CATALOG
from opencoat_runtime_core.pointcut import strategies as _strategies

# v0.1 §13.2 — one-line description per strategy, kept here so the CLI
# is a single source of truth for "what does each strategy do".
_POINTCUT_STRATEGY_DOC: dict[str, str] = {
    "lifecycle": "match agent lifecycle stage",
    "role": "match message role",
    "prompt_path": "match prompt-section path (runtime_prompt.…)",
    "keyword": "any/all keyword sets",
    "regex": "regex match against text payloads",
    "semantic": "semantic-intent match (LLM / embedding)",
    "structure": "structured field comparison (operators)",
    "token": "exact token / sub-token match",
    "claim": "match against asserted claims",
    "confidence": "operator + threshold over confidence score",
    "risk": "operator + level over risk",
    "history": "predicate over activation history",
}


def _inspect_joinpoints() -> int:
    for entry in JOINPOINT_CATALOG:
        desc = f" — {entry.description}" if entry.description else ""
        print(f"{entry.level.label:<16} {entry.name}{desc}")
    return 0


def _inspect_pointcuts() -> int:
    """List the 12 pointcut strategies bundled with ``opencoat_runtime_core``."""
    names = sorted(getattr(_strategies, "__all__", []))
    if not names:  # pragma: no cover — defensive, the package always exports them
        print("(no pointcut strategies registered)")
        return 1
    for name in names:
        desc = _POINTCUT_STRATEGY_DOC.get(name, "")
        suffix = f" — {desc}" if desc else ""
        print(f"{name:<14}{suffix}")
    return 0


def _handle(args: argparse.Namespace) -> int:
    if args.what == "joinpoints":
        return _inspect_joinpoints()
    if args.what == "pointcuts":
        return _inspect_pointcuts()
    print(f"inspect: unknown target {args.what!r}", file=sys.stderr)  # pragma: no cover
    return 2


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("inspect", help="introspect runtime tables")
    p.add_argument("what", choices=["joinpoints", "pointcuts"])
    p.set_defaults(func=_handle)


__all__ = ["register"]
