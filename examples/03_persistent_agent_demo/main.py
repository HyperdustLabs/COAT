"""CLI for the persistent-agent demo (M3 PR-16).

Run with::

    uv run python -m examples.03_persistent_agent_demo.main

Paths default to ``./.opencoat-persistent-demo/state.db`` and
``./.opencoat-persistent-demo/session.jsonl`` (parent dir is created
automatically). Override with ``--state-db`` / ``--session-log``, or pass
``--no-jsonl`` to skip the append-only session file.

Replay a recorded session (same semantics as ``opencoat replay``)::

    uv run python -m examples.03_persistent_agent_demo.main \\
        --replay ./.opencoat-persistent-demo/session.jsonl

Exit status for ``--replay``: ``0`` clean, ``1`` mismatches, ``2`` I/O
or parse errors.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from pathlib import Path

from .agent import PersistentAgent, TurnReport

DEFAULT_PROMPTS: tuple[str, ...] = (
    "Who invented the OpenCOAT runtime?",
    "Tell me how concerns get matched.",
)


def _format_report(report: TurnReport, *, turn_index: int) -> str:
    lines: list[str] = [
        f"── Turn {turn_index} " + "─" * 60,
        f"user: {report.user_text}",
        f"active concerns ({len(report.active_concern_ids)}): "
        + (", ".join(report.active_concern_ids) or "<none>"),
    ]
    if report.injection.injections:
        lines.append("injections:")
        for inj in report.injection.injections:
            level = inj.level or "<unset>"
            lines.append(
                f"  • [{inj.advice_type or 'unspecified'}] target={inj.target} "
                f"mode={inj.mode} level={level}"
            )
            lines.append(f"      {inj.content}")
    else:
        lines.append("injections: <none>")
    lines.append(f"response:\n  {report.response}")
    if report.verifications:
        lines.append("verifications:")
        for v in report.verifications:
            mark = "✓" if v.satisfied else "✗"
            lines.append(f"  {mark} {v.concern_id}: score={v.score:.2f} notes={v.notes!r}")
    else:
        lines.append("verifications: <none>")
    if report.reinforced_concern_ids:
        lines.append("reinforced: " + ", ".join(report.reinforced_concern_ids))
    else:
        lines.append("reinforced: <none>")
    return "\n".join(lines)


def run(
    prompts: Iterable[str],
    *,
    state_db: Path,
    session_log: Path | None,
) -> list[TurnReport]:
    """Run turns inside a context manager; return per-turn reports."""
    jsonl: Path | None = session_log
    with PersistentAgent(state_db, session_jsonl=jsonl) as agent:
        return [agent.handle(p) for p in prompts]


def _cmd_replay(path: Path, *, verbose: bool) -> int:
    from opencoat_runtime_storage.jsonl import replay_session_file

    try:
        result = replay_session_file(path)
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
        if verbose:
            print("    expected:", json.dumps(m.expected, indent=2), file=sys.stderr)
            print("    actual:  ", json.dumps(m.actual, indent=2), file=sys.stderr)
    return 0 if result.ok else 1


def main(argv: list[str] | None = None) -> int:
    default_dir = Path(".opencoat-persistent-demo")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "prompts",
        nargs="*",
        help="User prompts (default: two built-in demo strings).",
    )
    parser.add_argument(
        "--state-db",
        type=Path,
        default=default_dir / "state.db",
        help="SQLite file shared by SqliteConcernStore + SqliteDCNStore.",
    )
    parser.add_argument(
        "--session-log",
        type=Path,
        default=default_dir / "session.jsonl",
        help="Append-only JSONL session log (ADR 0007). Ignored with --no-jsonl.",
    )
    parser.add_argument(
        "--no-jsonl",
        action="store_true",
        help="Do not write a session.jsonl file.",
    )
    parser.add_argument(
        "--replay",
        type=Path,
        metavar="SESSION.jsonl",
        help="Parse and replay a session file; do not run live prompts.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="With --replay, dump expected vs actual JSON per mismatch.",
    )
    args = parser.parse_args(argv)

    if args.replay is not None:
        return _cmd_replay(args.replay, verbose=args.verbose)

    prompts = tuple(args.prompts) or DEFAULT_PROMPTS
    log_path: Path | None = None if args.no_jsonl else args.session_log
    reports = run(prompts, state_db=args.state_db, session_log=log_path)

    print(f"state-db: {args.state_db.resolve()}")
    if log_path is not None:
        print(f"session-log: {log_path.resolve()}")
    else:
        print("session-log: <disabled>")
    print()

    for index, report in enumerate(reports, start=1):
        print(_format_report(report, turn_index=index))
        print()
    print(
        "Summary: "
        f"{len(reports)} turn(s), "
        f"{sum(len(r.injection.injections) for r in reports)} injections, "
        f"{sum(r.passed_verifications for r in reports)} / "
        f"{sum(len(r.verifications) for r in reports)} verifications passed, "
        f"{sum(len(r.reinforced_concern_ids) for r in reports)} reinforcements."
    )
    if log_path is not None:
        print(f"\nReplay: opencoat replay {log_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
