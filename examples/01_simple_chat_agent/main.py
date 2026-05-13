"""Command-line entry point for the simple chat-agent example.

Run with::

    uv run python -m examples.01_simple_chat_agent.main

Or with a specific prompt::

    uv run python -m examples.01_simple_chat_agent.main "What is OpenCOAT?"

The output is intentionally readable: one section per turn showing the
matched concerns, the woven injection (target / mode / level / content),
and the verifier verdicts. No external network is touched — the runtime
is wired with the stub LLM and the in-memory stores.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable

from .agent import SimpleChatAgent, TurnReport

DEFAULT_PROMPTS: tuple[str, ...] = (
    "Who invented the OpenCOAT runtime?",
    "Tell me how concerns get matched.",
    "What is the user's email address?",
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
            # Envelopes use ``use_enum_values=True`` so the enum-valued
            # fields are already plain strings here.
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
    return "\n".join(lines)


def run(prompts: Iterable[str]) -> list[TurnReport]:
    """Drive ``SimpleChatAgent`` against ``prompts`` and return per-turn reports.

    Exposed (in addition to :func:`main`) so the smoke test can collect
    structured results without parsing stdout.
    """
    agent = SimpleChatAgent()
    reports: list[TurnReport] = []
    for prompt in prompts:
        reports.append(agent.handle(prompt))
    return reports


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "prompts",
        nargs="*",
        help="One or more user prompts. Defaults to a built-in demo set.",
    )
    args = parser.parse_args(argv)

    prompts = tuple(args.prompts) or DEFAULT_PROMPTS
    reports = run(prompts)
    for index, report in enumerate(reports, start=1):
        print(_format_report(report, turn_index=index))
        print()
    print(
        "Summary: "
        f"{len(reports)} turn(s), "
        f"{sum(len(r.injection.injections) for r in reports)} injections, "
        f"{sum(r.passed_verifications for r in reports)} / "
        f"{sum(len(r.verifications) for r in reports)} verifications passed."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
