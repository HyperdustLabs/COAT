"""Append-only JSONL session recorder (M3 PR-15).

Writes one JSON object per line in chronological order:

1. Optional ``session`` header (concern seeds + metadata) — emitted
   once on :meth:`SessionJsonlRecorder.write_session_header`.
2. For each turn: a ``joinpoint`` record followed by an ``injection``
   record (the latter may carry ``null`` when the runtime returned
   ``None`` with ``return_none_when_empty=True``).

Thread-safe: concurrent hosts can call :meth:`record_turn` from worker
threads; all writes serialize on an :class:`RLock`.

The file is opened in append mode — multiple processes appending to
the same path is *not* supported (no POSIX ``O_APPEND`` cross-process
guarantee in the stdlib wrapper); single-process multi-thread only.

On ``__enter__``, the recorder scans any existing file so append
resumes monotonic ``seq`` values and :meth:`write_session_header` is a
no-op when a ``session`` line already exists at the beginning of the
file (re-open / crash-restart on the same path).  Calling
``write_session_header`` when the file already begins with turn
records (``joinpoint`` / ``injection``) raises :class:`ValueError` —
appending a header at EOF would break replay.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterable
from pathlib import Path
from typing import Any, TextIO

from COAT_runtime_protocol import Concern, ConcernInjection, JoinpointEvent

from .records import EVENT_INJECTION, EVENT_JOINPOINT, EVENT_SESSION, RECORD_VERSION


class SessionJsonlRecorder:
    """Append JSONL records for offline replay / audit (ADR 0007)."""

    def __init__(self, path: str | Path, *, session_id: str) -> None:
        self._path = Path(path)
        self._session_id = session_id
        self._lock = threading.RLock()
        self._seq = 0
        self._fp: TextIO | None = None
        self._disk_has_session_header = False
        self._bof_event: str | None = None
        self._header_written_this_open = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def __enter__(self) -> SessionJsonlRecorder:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            max_seq, bof_event = self._scan_existing()
            self._seq = max_seq
            self._bof_event = bof_event
            self._disk_has_session_header = bof_event == EVENT_SESSION
            self._header_written_this_open = False
            self._fp = self._path.open("a", encoding="utf-8")
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        with self._lock:
            if self._fp is not None:
                self._fp.flush()
                self._fp.close()
                self._fp = None

    def _ensure_open(self) -> TextIO:
        if self._fp is None:
            msg = "SessionJsonlRecorder is not open — use a context manager or call open()"
            raise RuntimeError(msg)
        return self._fp

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _scan_existing(self) -> tuple[int, str | None]:
        """Return ``(max_seq, first_non_blank_event)`` for an on-disk file."""
        if not self._path.exists() or self._path.stat().st_size == 0:
            return 0, None
        max_seq = 0
        first_event: str | None = None
        with self._path.open(encoding="utf-8") as rf:
            for raw in rf:
                line = raw.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if first_event is None:
                    ev = rec.get("event")
                    first_event = ev if isinstance(ev, str) else None
                s = rec.get("seq")
                if isinstance(s, int):
                    max_seq = max(max_seq, s)
        return max_seq, first_event

    def _write(self, payload: dict[str, Any]) -> None:
        fp = self._ensure_open()
        line = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        fp.write(line + "\n")
        fp.flush()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def write_session_header(
        self,
        *,
        concerns: Iterable[Concern] | None = None,
        protocol_schema_version: str = "0.1.0",
    ) -> None:
        """Emit the optional ``session`` line (call at most once per open).

        Seeds replay with the same :class:`Concern` envelopes the host
        had when the session was recorded.  Omit entirely if the file
        is only used for joinpoint-level smoke tests with an empty
        store.

        If the append target already has a ``session`` line at the
        start of the file (e.g. recorder re-opened on the same path),
        this method is a no-op so replay ordering stays valid.

        Raises :class:`ValueError` if the file already begins with turn
        records — a header cannot be appended after the fact.
        """
        with self._lock:
            if self._disk_has_session_header:
                return
            if self._header_written_this_open:
                raise RuntimeError("session header already written for this recorder")
            if self._bof_event is not None and self._bof_event != EVENT_SESSION:
                msg = (
                    "cannot write session header: file already begins with "
                    f"{self._bof_event!r} records — use a new path or omit write_session_header"
                )
                raise ValueError(msg)
            self._header_written_this_open = True
            dumped = [c.model_dump(mode="json") for c in (concerns or ())]
            self._write(
                {
                    "record_version": RECORD_VERSION,
                    "seq": self._next_seq(),
                    "event": EVENT_SESSION,
                    "session_id": self._session_id,
                    "concerns": dumped,
                    "protocol_schema_version": protocol_schema_version,
                }
            )
            self._bof_event = EVENT_SESSION

    def record_turn(
        self,
        joinpoint: JoinpointEvent,
        injection: ConcernInjection | None,
        *,
        return_none_when_empty: bool = False,
    ) -> None:
        """Append one joinpoint + one injection pair (ADR 0007)."""
        with self._lock:
            self._write(
                {
                    "record_version": RECORD_VERSION,
                    "seq": self._next_seq(),
                    "event": EVENT_JOINPOINT,
                    "session_id": self._session_id,
                    "joinpoint": joinpoint.model_dump(mode="json"),
                    "return_none_when_empty": return_none_when_empty,
                }
            )
            inj_payload: dict[str, Any] | None = (
                None if injection is None else injection.model_dump(mode="json")
            )
            self._write(
                {
                    "record_version": RECORD_VERSION,
                    "seq": self._next_seq(),
                    "event": EVENT_INJECTION,
                    "session_id": self._session_id,
                    "injection": inj_payload,
                }
            )
            if self._bof_event is None:
                self._bof_event = EVENT_JOINPOINT


__all__ = ["SessionJsonlRecorder"]
