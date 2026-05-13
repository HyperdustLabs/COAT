"""Append-only JSONL session log — replay and audit (M3 PR-15).

Implements ADR 0007: one ``joinpoint`` line + one ``injection`` line per
turn, optional ``session`` header with concern seeds, and a small replay
API that re-drives joinpoints through a fresh in-memory runtime.

Typical recording::

    from opencoat_runtime_storage.jsonl import SessionJsonlRecorder

    with SessionJsonlRecorder(\"session.jsonl\", session_id=\"sess-1\") as rec:
        rec.write_session_header(concerns=seed_concerns)
        inj = runtime.on_joinpoint(jp)
        rec.record_turn(jp, inj)

Typical offline replay::

    from opencoat_runtime_storage.jsonl import replay_session_file

    result = replay_session_file(\"session.jsonl\")
    assert result.ok
"""

from .reading import ParsedSession, iter_jsonl_records, parse_session_file, parse_session_records
from .recorder import SessionJsonlRecorder
from .records import (
    EVENT_INJECTION,
    EVENT_JOINPOINT,
    EVENT_SESSION,
    RECORD_VERSION,
    EventType,
)
from .replay import (
    ReplayResult,
    TurnMismatch,
    build_runtime_for_replay,
    replay_parsed_session,
    replay_session_file,
)

__all__ = [
    "EVENT_INJECTION",
    "EVENT_JOINPOINT",
    "EVENT_SESSION",
    "RECORD_VERSION",
    "EventType",
    "ParsedSession",
    "ReplayResult",
    "SessionJsonlRecorder",
    "TurnMismatch",
    "build_runtime_for_replay",
    "iter_jsonl_records",
    "parse_session_file",
    "parse_session_records",
    "replay_parsed_session",
    "replay_session_file",
]
