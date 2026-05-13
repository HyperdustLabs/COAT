"""Tests for ``opencoat replay`` (M3 PR-15)."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from opencoat_runtime_cli.commands import replay_cmd
from opencoat_runtime_core import OpenCOATRuntime, RuntimeConfig
from opencoat_runtime_core.llm import StubLLMClient
from opencoat_runtime_protocol import (
    Advice,
    AdviceType,
    Concern,
    JoinpointEvent,
    Pointcut,
    WeavingLevel,
    WeavingOperation,
    WeavingPolicy,
)
from opencoat_runtime_protocol.envelopes import PointcutMatch
from opencoat_runtime_storage.jsonl import SessionJsonlRecorder
from opencoat_runtime_storage.memory import MemoryConcernStore, MemoryDCNStore


def _jp() -> JoinpointEvent:
    return JoinpointEvent(
        id="jp-cli",
        level=2,
        name="before_response",
        host="cli-test",
        agent_session_id="sess",
        ts=datetime(2026, 5, 11, 15, 0, tzinfo=UTC),
        payload={"text": "refund help", "raw_text": "refund help"},
    )


def _concern() -> Concern:
    return Concern(
        id="c-cli",
        name="Rule",
        description="d",
        pointcut=Pointcut(match=PointcutMatch(any_keywords=["refund"])),
        advice=Advice(type=AdviceType.REASONING_GUIDANCE, content="x"),
        weaving_policy=WeavingPolicy(
            mode=WeavingOperation.INSERT,
            level=WeavingLevel.PROMPT_LEVEL,
            target="reasoning.hints",
            priority=0.5,
        ),
    )


def test_replay_cmd_exits_zero_on_match(tmp_path: Path) -> None:
    path = tmp_path / "s.jsonl"
    c = _concern()
    rt = OpenCOATRuntime(
        RuntimeConfig(),
        concern_store=MemoryConcernStore(),
        dcn_store=MemoryDCNStore(),
        llm=StubLLMClient(),
    )
    rt.concern_store.upsert(c)
    jp = _jp()
    inj = rt.on_joinpoint(jp)
    assert inj is not None

    with SessionJsonlRecorder(path, session_id="s") as rec:
        rec.write_session_header(concerns=[c])
        rec.record_turn(jp, inj)

    args = argparse.Namespace(path=str(path), verbose=False)
    assert replay_cmd._handle(args) == 0
