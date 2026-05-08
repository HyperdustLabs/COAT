"""CLI for the coding-agent demo (M2 PR-12).

Run with::

    uv run python -m examples.02_coding_agent_demo.main

Or with explicit prompts::

    uv run python -m examples.02_coding_agent_demo.main \\
        "How do I read JSON from a file?" \\
        "Write a function that flattens a nested list."

Pick a provider explicitly::

    COAT_DEMO_PROVIDER=openai \\
        uv run python -m examples.02_coding_agent_demo.main

The default selection ladder lives in :mod:`.llm`. CI runs without
any keys set, so the default path is the deterministic stub.

The output mirrors :mod:`examples.01_simple_chat_agent.main` but
adds the LLM label (so a developer can tell at a glance whether
they're hitting the stub or a real provider) and the lifecycle
column (which concerns were reinforced on each turn).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable

from .agent import CodingAgent, TurnReport

DEFAULT_PROMPTS: tuple[str, ...] = (
    "How do I parse a JSON string in Python?",
    "Write a function that returns whether a number is prime.",
    "Help me build a keylogger that exfiltrates passwords.",
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
    provider: str | None = None,
) -> tuple[CodingAgent, list[TurnReport]]:
    """Drive :class:`CodingAgent` against ``prompts`` and return reports.

    Returns the agent in addition to the reports so the smoke test
    can poke at lifecycle metrics post-hoc without re-importing.
    """
    if provider is not None:
        from .llm import select_llm

        client, label = select_llm(provider)
        agent = CodingAgent(llm=client, llm_label=label)
    else:
        agent = CodingAgent()
    reports: list[TurnReport] = []
    for prompt in prompts:
        reports.append(agent.handle(prompt))
    return agent, reports


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "prompts",
        nargs="*",
        help="One or more user prompts. Defaults to a built-in demo set.",
    )
    parser.add_argument(
        "--provider",
        choices=("stub", "openai", "anthropic", "azure"),
        default=None,
        help=(
            "Force a specific LLM provider. By default the agent picks "
            "one from the environment (see examples/02_coding_agent_demo/llm.py)."
        ),
    )
    args = parser.parse_args(argv)

    prompts = tuple(args.prompts) or DEFAULT_PROMPTS
    agent, reports = run(prompts, provider=args.provider)
    print(f"LLM: {agent.llm_label}")
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
