"""PersistentAgent — sqlite stores + optional JSONL session log (M3 PR-16).

Wires the same turn shape as :class:`examples.01_simple_chat_agent.SimpleChatAgent`
but swaps :class:`~opencoat_runtime_storage.memory.MemoryConcernStore` /
:class:`~opencoat_runtime_storage.memory.MemoryDCNStore` for
:class:`~opencoat_runtime_storage.sqlite.SqliteConcernStore` /
:class:`~opencoat_runtime_storage.sqlite.SqliteDCNStore` pointing at a **single**
SQLite file (see storage README).

Optionally appends an ADR-0007 JSONL session via
:class:`~opencoat_runtime_storage.jsonl.SessionJsonlRecorder` so
``opencoat replay session.jsonl`` can diff injections offline.

**Seeding:** ``concerns=None`` upserts :func:`seed_concerns` only when the
on-disk store is empty — a second process (or a second in-process agent)
reusing the same ``state_db`` therefore keeps the persisted rows instead
of blindly re-inserting demo fixtures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from opencoat_runtime_core import OpenCOATRuntime, RuntimeConfig
from opencoat_runtime_core.concern.lifecycle import ConcernLifecycleManager
from opencoat_runtime_core.concern.verifier import ConcernVerifier, VerificationResult
from opencoat_runtime_core.llm import StubLLMClient
from opencoat_runtime_protocol import (
    Concern,
    ConcernInjection,
    ConcernVector,
    JoinpointEvent,
)
from opencoat_runtime_storage.jsonl import SessionJsonlRecorder
from opencoat_runtime_storage.sqlite import SqliteConcernStore, SqliteDCNStore

from .concerns import seed_concerns


@dataclass(frozen=True)
class TurnReport:
    """One turn — mirrors the M1 example with an optional reinforcement list."""

    user_text: str
    response: str
    injection: ConcernInjection
    vector: ConcernVector
    verifications: list[VerificationResult] = field(default_factory=list)
    reinforced_concern_ids: list[str] = field(default_factory=list)

    @property
    def active_concern_ids(self) -> list[str]:
        return [a.concern_id for a in self.vector.active_concerns]

    @property
    def passed_verifications(self) -> int:
        return sum(1 for v in self.verifications if v.satisfied)


class PersistentAgent:
    """Host with sqlite persistence and optional JSONL recording.

    Use as a context manager when ``session_jsonl`` is set so the recorder
    is opened, the ``session`` header is written once, and handles flush on
    exit. SQLite connections are always closed on context exit.
    """

    def __init__(
        self,
        state_db: str | Path,
        *,
        session_jsonl: str | Path | None = None,
        concerns: list[Concern] | None = None,
        session_id: str | None = None,
        verifier: ConcernVerifier | None = None,
        lifecycle: ConcernLifecycleManager | None = None,
    ) -> None:
        self._state_db = Path(state_db)
        self._session_jsonl = Path(session_jsonl) if session_jsonl is not None else None
        self._session_id = session_id or f"session-{uuid4().hex[:8]}"

        self._concern_store = SqliteConcernStore(self._state_db)
        self._dcn_store = SqliteDCNStore(self._state_db)
        self._runtime = OpenCOATRuntime(
            RuntimeConfig(),
            concern_store=self._concern_store,
            dcn_store=self._dcn_store,
            llm=StubLLMClient(),
        )
        self._verifier = verifier or ConcernVerifier(llm=self._runtime._llm)  # type: ignore[attr-defined]
        self._lifecycle = lifecycle or ConcernLifecycleManager(
            concern_store=self._concern_store,
            dcn_store=self._dcn_store,
        )
        self._recorder: SessionJsonlRecorder | None = None

        self._seed_store(concerns)

    def _seed_store(self, concerns: list[Concern] | None) -> None:
        if concerns is None:
            if list(self._concern_store.iter_all()):
                return
            to_upsert = seed_concerns()
        elif concerns == []:
            to_upsert = []
        else:
            to_upsert = list(concerns)
        for c in to_upsert:
            self._concern_store.upsert(c)

    def __enter__(self) -> PersistentAgent:
        if self._session_jsonl is not None:
            self._recorder = SessionJsonlRecorder(self._session_jsonl, session_id=self._session_id)
            self._recorder.__enter__()
            self._recorder.write_session_header(
                concerns=list(self._concern_store.iter_all()),
            )
        return self

    def __exit__(self, *exc: object) -> None:
        if self._recorder is not None:
            self._recorder.__exit__(*exc)
            self._recorder = None
        self._concern_store.close()
        self._dcn_store.close()

    @property
    def runtime(self) -> OpenCOATRuntime:
        return self._runtime

    @property
    def session_id(self) -> str:
        return self._session_id

    def handle(self, user_text: str) -> TurnReport:
        if self._session_jsonl is not None and self._recorder is None:
            msg = (
                "session_jsonl was set — use ``with PersistentAgent(...) as agent`` "
                "so the JSONL recorder opens before handle()."
            )
            raise RuntimeError(msg)

        joinpoint = JoinpointEvent(
            id=f"jp-{uuid4().hex[:12]}",
            level=2,
            name="before_response",
            host="example.persistent_agent_demo",
            agent_session_id=self._session_id,
            ts=datetime.now(UTC),
            payload={"raw_text": user_text, "text": user_text},
        )

        injection = self._runtime.on_joinpoint(joinpoint)
        assert injection is not None
        vector = self._runtime.current_vector()
        assert vector is not None

        if self._recorder is not None:
            self._recorder.record_turn(joinpoint, injection)

        response = self._compose_response(user_text, injection)
        verifications = self._verifier.verify_turn(
            active=vector,
            concerns=list(self._concern_store.iter_all()),
            host_output=response,
        )

        reinforced: list[str] = []
        for active in vector.active_concerns:
            stored = self._concern_store.get(active.concern_id)
            if stored is None:
                continue
            self._lifecycle.reinforce(stored)
            reinforced.append(active.concern_id)

        return TurnReport(
            user_text=user_text,
            response=response,
            injection=injection,
            vector=vector,
            verifications=verifications,
            reinforced_concern_ids=reinforced,
        )

    def _compose_response(self, user_text: str, injection: ConcernInjection) -> str:
        directives = "\n".join(
            f"- {inj.advice_type or 'unspecified'}: {inj.content}" for inj in injection.injections
        )
        return f"You asked: {user_text}\nFollowing guidance:\n{directives}\nAnswer: see [1]."


__all__ = ["PersistentAgent", "TurnReport"]
