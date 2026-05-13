"""Wire-format constants for the JSONL session log (M3 PR-15).

Each physical line in a ``*.jsonl`` file is one JSON object (UTF-8,
no pretty-print) so Unix ``tail -f`` / ``wc -l`` / ``jq`` work as
expected.  ``record_version`` bumps only when the envelope shape
changes incompatibly — bump it together with replay tests whenever
you add a new mandatory field.

See :mod:`docs.adr.0007-jsonl-replay-as-debug-source` for the product
rationale.
"""

from __future__ import annotations

from typing import Final, Literal

# Bump only on incompatible envelope changes (new mandatory fields,
# renamed keys, semantic changes). Replay refuses unknown versions
# unless explicitly upgraded.
RECORD_VERSION: Final[int] = 1

EventType = Literal["session", "joinpoint", "injection"]

EVENT_SESSION: Final[Literal["session"]] = "session"
EVENT_JOINPOINT: Final[Literal["joinpoint"]] = "joinpoint"
EVENT_INJECTION: Final[Literal["injection"]] = "injection"

__all__ = [
    "EVENT_INJECTION",
    "EVENT_JOINPOINT",
    "EVENT_SESSION",
    "RECORD_VERSION",
    "EventType",
]
