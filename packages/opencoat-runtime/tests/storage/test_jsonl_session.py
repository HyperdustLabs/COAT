"""Tests for JSONL session recording + replay (M3 PR-15)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
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
from opencoat_runtime_storage.jsonl import (
    SessionJsonlRecorder,
    build_runtime_for_replay,
    iter_jsonl_records,
    parse_session_file,
    parse_session_records,
    replay_parsed_session,
    replay_session_file,
)
from opencoat_runtime_storage.memory import MemoryConcernStore, MemoryDCNStore


def _jp(text: str, *, jid: str = "jp-1") -> JoinpointEvent:
    return JoinpointEvent(
        id=jid,
        level=2,
        name="before_response",
        host="test",
        agent_session_id="sess",
        ts=datetime(2026, 5, 11, 12, 0, tzinfo=UTC),
        payload={"text": text, "raw_text": text},
    )


def _concern(cid: str = "c1", *, keyword: str = "refund") -> Concern:
    return Concern(
        id=cid,
        name="Refund rule",
        description="When user mentions refunds, remind policy.",
        pointcut=Pointcut(match=PointcutMatch(any_keywords=[keyword])),
        advice=Advice(type=AdviceType.REASONING_GUIDANCE, content="Be polite about refunds."),
        weaving_policy=WeavingPolicy(
            mode=WeavingOperation.INSERT,
            level=WeavingLevel.PROMPT_LEVEL,
            target="reasoning.hints",
            priority=0.5,
        ),
    )


def test_parse_empty_file(tmp_path: Path) -> None:
    p = tmp_path / "empty.jsonl"
    p.write_text("", encoding="utf-8")
    parsed = parse_session_file(p)
    assert parsed.turns == []
    assert parsed.concerns == []


def test_record_and_replay_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "session.jsonl"
    concern = _concern()
    rt = OpenCOATRuntime(
        RuntimeConfig(),
        concern_store=MemoryConcernStore(),
        dcn_store=MemoryDCNStore(),
        llm=StubLLMClient(),
    )
    rt.concern_store.upsert(concern)

    jp = _jp("I need a refund on my order")
    inj = rt.on_joinpoint(jp)
    assert inj is not None

    with SessionJsonlRecorder(path, session_id="sess-a") as rec:
        rec.write_session_header(concerns=[concern])
        rec.record_turn(jp, inj)

    result = replay_session_file(path)
    assert result.ok
    assert result.turns == 1


def test_replay_detects_store_drift(tmp_path: Path) -> None:
    path = tmp_path / "session.jsonl"
    concern = _concern()
    rt = OpenCOATRuntime(
        RuntimeConfig(),
        concern_store=MemoryConcernStore(),
        dcn_store=MemoryDCNStore(),
        llm=StubLLMClient(),
    )
    rt.concern_store.upsert(concern)
    jp = _jp("refund please")
    golden = rt.on_joinpoint(jp)
    assert golden is not None

    with SessionJsonlRecorder(path, session_id="s") as rec:
        rec.write_session_header(concerns=[concern])
        rec.record_turn(jp, golden)

    parsed = parse_session_file(path)
    empty_rt = build_runtime_for_replay([])
    bad = replay_parsed_session(empty_rt, parsed)
    assert not bad.ok
    assert len(bad.mismatches) == 1


def test_return_none_when_empty_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "none.jsonl"
    rt = OpenCOATRuntime(
        RuntimeConfig(),
        concern_store=MemoryConcernStore(),
        dcn_store=MemoryDCNStore(),
        llm=StubLLMClient(),
    )
    jp = _jp("no keywords here", jid="jp-empty")
    actual = rt.on_joinpoint(jp, return_none_when_empty=True)
    assert actual is None

    with SessionJsonlRecorder(path, session_id="s") as rec:
        rec.write_session_header(concerns=[])
        rec.record_turn(jp, actual, return_none_when_empty=True)

    result = replay_session_file(path)
    assert result.ok


def test_parse_rejects_unknown_record_version() -> None:
    bad = [{"record_version": 999, "event": "session", "seq": 1, "session_id": "x", "concerns": []}]
    with pytest.raises(ValueError, match="record_version"):
        parse_session_records(bad)


def test_parse_rejects_missing_injection(tmp_path: Path) -> None:
    path = tmp_path / "bad.jsonl"
    jp = _jp("x").model_dump(mode="json")
    path.write_text(
        json.dumps(
            {
                "record_version": 1,
                "seq": 1,
                "event": "joinpoint",
                "session_id": "s",
                "joinpoint": jp,
                "return_none_when_empty": False,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="missing injection"):
        parse_session_file(path)


def test_iter_jsonl_skips_blank_lines(tmp_path: Path) -> None:
    p = tmp_path / "lines.jsonl"
    p.write_text('\n{"a": 1}\n\n{"b": 2}\n', encoding="utf-8")
    rows = list(iter_jsonl_records(p))
    assert rows == [{"a": 1}, {"b": 2}]


def test_session_header_idempotent_guard(tmp_path: Path) -> None:
    path = tmp_path / "s.jsonl"
    c = _concern()
    with SessionJsonlRecorder(path, session_id="s") as rec:
        rec.write_session_header(concerns=[c])
        with pytest.raises(RuntimeError, match="header"):
            rec.write_session_header(concerns=[c])


def test_reopen_same_path_write_session_header_no_second_session_line(
    tmp_path: Path,
) -> None:
    """Codex P2: append target may already have a BOF ``session`` line."""
    path = tmp_path / "s.jsonl"
    c = _concern()
    rt = OpenCOATRuntime(
        RuntimeConfig(),
        concern_store=MemoryConcernStore(),
        dcn_store=MemoryDCNStore(),
        llm=StubLLMClient(),
    )
    rt.concern_store.upsert(c)
    jp1 = _jp("refund please", jid="jp-a")
    inj1 = rt.on_joinpoint(jp1)
    assert inj1 is not None

    with SessionJsonlRecorder(path, session_id="s") as rec:
        rec.write_session_header(concerns=[c])
        rec.record_turn(jp1, inj1)

    jp2 = _jp("another refund", jid="jp-b")
    inj2 = rt.on_joinpoint(jp2)
    assert inj2 is not None

    with SessionJsonlRecorder(path, session_id="s") as rec2:
        rec2.write_session_header(concerns=[c])
        rec2.record_turn(jp2, inj2)

    rows = list(iter_jsonl_records(path))
    assert sum(1 for r in rows if r.get("event") == "session") == 1
    assert replay_session_file(path).ok
    assert len(parse_session_file(path).turns) == 2


def test_write_session_header_after_record_turn_same_open_raises(
    tmp_path: Path,
) -> None:
    path = tmp_path / "s.jsonl"
    c = _concern()
    rt = OpenCOATRuntime(
        RuntimeConfig(),
        concern_store=MemoryConcernStore(),
        dcn_store=MemoryDCNStore(),
        llm=StubLLMClient(),
    )
    rt.concern_store.upsert(c)
    jp = _jp("refund", jid="jp-1")
    inj = rt.on_joinpoint(jp)
    assert inj is not None
    with SessionJsonlRecorder(path, session_id="s") as rec:
        rec.record_turn(jp, inj)
        with pytest.raises(ValueError, match="cannot write session header"):
            rec.write_session_header(concerns=[c])


def test_replay_parsed_session_custom_runtime(tmp_path: Path) -> None:
    path = tmp_path / "s.jsonl"
    concern = _concern()
    rt = build_runtime_for_replay([concern])
    jp = _jp("refund policy")
    inj = rt.on_joinpoint(jp)
    assert inj is not None

    with SessionJsonlRecorder(path, session_id="s2") as rec:
        rec.record_turn(jp, inj)

    parsed = parse_session_file(path)
    assert parsed.concerns == []
    out = replay_parsed_session(rt, parsed)
    assert out.ok
