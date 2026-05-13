"""Read and parse JSONL session files (M3 PR-15).

Pure functions — no I/O hidden inside parsers so tests can feed
in-memory ``list[dict]`` without touching the filesystem.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from opencoat_runtime_protocol import Concern, ConcernInjection, JoinpointEvent

from .records import EVENT_INJECTION, EVENT_JOINPOINT, EVENT_SESSION, RECORD_VERSION


@dataclass
class ParsedSession:
    """Structured view of a ``*.jsonl`` session file."""

    session_id: str | None = None
    concerns: list[Concern] = field(default_factory=list)
    protocol_schema_version: str | None = None
    turns: list[tuple[JoinpointEvent, ConcernInjection | None, bool]] = field(default_factory=list)
    """Each tuple is ``(joinpoint, expected_injection_or_None, return_none_when_empty)``."""


def iter_jsonl_records(path: str | Path) -> Iterator[dict[str, Any]]:
    """Yield each JSON object from a UTF-8 JSONL file, skipping blank lines."""
    p = Path(path)
    with p.open(encoding="utf-8") as fp:
        for raw in fp:
            line = raw.strip()
            if not line:
                continue
            yield json.loads(line)


def parse_session_records(records: list[dict[str, Any]]) -> ParsedSession:
    """Parse a list of wire records into :class:`ParsedSession`.

    Raises ``ValueError`` on malformed ordering or unknown
    ``record_version``.
    """
    out = ParsedSession()
    i = 0
    n = len(records)

    if n == 0:
        return out

    if records[0].get("event") == EVENT_SESSION:
        sess = records[0]
        _check_record_version(sess)
        out.session_id = sess.get("session_id")
        out.protocol_schema_version = sess.get("protocol_schema_version")
        for blob in sess.get("concerns") or []:
            out.concerns.append(Concern.model_validate(blob))
        i = 1

    turn_idx = 0
    while i < n:
        rec = records[i]
        _check_record_version(rec)
        ev = rec.get("event")
        if ev != EVENT_JOINPOINT:
            raise ValueError(
                f"expected joinpoint record at index {i}, got event={ev!r} (turn {turn_idx})"
            )
        jp = JoinpointEvent.model_validate(rec["joinpoint"])
        ret_none = bool(rec.get("return_none_when_empty", False))
        i += 1
        if i >= n:
            raise ValueError(f"missing injection record after joinpoint at turn {turn_idx}")
        rec2 = records[i]
        _check_record_version(rec2)
        if rec2.get("event") != EVENT_INJECTION:
            raise ValueError(
                f"expected injection record after joinpoint at turn {turn_idx}, "
                f"got event={rec2.get('event')!r}"
            )
        inj_raw = rec2.get("injection")
        inj: ConcernInjection | None = (
            None if inj_raw is None else ConcernInjection.model_validate(inj_raw)
        )
        out.turns.append((jp, inj, ret_none))
        i += 1
        turn_idx += 1

    return out


def parse_session_file(path: str | Path) -> ParsedSession:
    """Parse a JSONL file from disk."""
    return parse_session_records(list(iter_jsonl_records(path)))


def _check_record_version(rec: dict[str, Any]) -> None:
    ver = rec.get("record_version")
    if ver is None:
        raise ValueError("record missing record_version")
    if int(ver) != RECORD_VERSION:
        raise ValueError(f"unsupported record_version {ver!r} (expected {RECORD_VERSION})")


__all__ = [
    "ParsedSession",
    "iter_jsonl_records",
    "parse_session_file",
    "parse_session_records",
]
