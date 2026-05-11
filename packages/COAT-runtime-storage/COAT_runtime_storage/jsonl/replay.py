"""Replay a JSONL session against a :class:`COATRuntime` (M3 PR-15).

Implements the offline half of ADR 0007: re-drive recorded joinpoints
through a fresh runtime and compare the resulting injections to the
golden copies stored next to each joinpoint in the log.

The default entrypoint :func:`replay_session_file` builds an in-memory
runtime seeded from the optional ``session`` header (concern upserts)
plus a deterministic :class:`~COAT_runtime_core.llm.StubLLMClient`.
Hosts that need a different baseline (e.g. sqlite stores) can call
:func:`replay_parsed_session` with a pre-constructed runtime instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from COAT_runtime_core import COATRuntime, RuntimeConfig
from COAT_runtime_core.llm import StubLLMClient
from COAT_runtime_protocol import Concern, ConcernInjection

from COAT_runtime_storage.memory import MemoryConcernStore, MemoryDCNStore

from .reading import ParsedSession, parse_session_file


@dataclass
class TurnMismatch:
    """One turn where the live injection differed from the recording."""

    turn_index: int
    joinpoint_id: str
    expected: dict[str, Any] | None
    actual: dict[str, Any] | None
    detail: str


@dataclass
class ReplayResult:
    """Aggregate outcome of a full-session replay."""

    turns: int
    mismatches: list[TurnMismatch] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.mismatches


def build_runtime_for_replay(concerns: list[Concern]) -> COATRuntime:
    """Construct the canonical replay baseline (memory + stub LLM)."""
    store = MemoryConcernStore()
    for c in concerns:
        store.upsert(c)
    return COATRuntime(
        RuntimeConfig(),
        concern_store=store,
        dcn_store=MemoryDCNStore(),
        llm=StubLLMClient(),
    )


def replay_parsed_session(runtime: COATRuntime, session: ParsedSession) -> ReplayResult:
    """Re-run every recorded turn and diff injections."""
    mismatches: list[TurnMismatch] = []
    for idx, (jp, expected, ret_none) in enumerate(session.turns):
        actual = runtime.on_joinpoint(jp, return_none_when_empty=ret_none)
        exp_norm = _injection_fingerprint(expected)
        act_norm = _injection_fingerprint(actual)
        if exp_norm != act_norm:
            mismatches.append(
                TurnMismatch(
                    turn_index=idx,
                    joinpoint_id=jp.id,
                    expected=exp_norm,
                    actual=act_norm,
                    detail="injection payload differs",
                )
            )
    return ReplayResult(turns=len(session.turns), mismatches=mismatches)


def _injection_fingerprint(inj: ConcernInjection | None) -> dict[str, Any] | None:
    """Stable projection for equality — wall-clock ``ts`` is excluded.

    The weaver stamps ``ConcernInjection.ts`` with real time on every
    run; two byte-identical replays would still differ on that field.
    """
    if inj is None:
        return None
    d = inj.model_dump(mode="json")
    d.pop("ts", None)
    return d


def replay_session_file(path: str | Path) -> ReplayResult:
    """Parse ``path`` and replay using concerns from the ``session`` header."""
    parsed = parse_session_file(path)
    runtime = build_runtime_for_replay(parsed.concerns)
    return replay_parsed_session(runtime, parsed)


__all__ = [
    "ReplayResult",
    "TurnMismatch",
    "build_runtime_for_replay",
    "replay_parsed_session",
    "replay_session_file",
]
