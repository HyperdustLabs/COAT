"""End-to-end tests for :meth:`Client.extract_concerns` (M5 PR-48).

The headline contract the daemon's ``concern.extract`` RPC promises
host code is: "give me natural-language text plus an ``origin``, get
back validated Concern envelopes plus a record of what got rejected,
and the daemon has already upserted the candidates so the next
``joinpoint.submit`` sees them".

These tests stand up a real :class:`HttpServer` for the wire path
and a bare in-proc transport for the embedded path, prove both go
through ``extract_concerns`` identically, and pin the side-effect
contracts (upsert by default, dry-run skips, error mapping).

The runtime is constructed with a scripted :class:`StubLLMClient` so
the extractor sees a deterministic ``structured()`` reply — without
that, the stub default is ``{}`` and every candidate would be
silently skipped, masking happy-path bugs.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator

import pytest
from opencoat_runtime_core import OpenCOATRuntime
from opencoat_runtime_core.llm import StubLLMClient
from opencoat_runtime_daemon.ipc.http_server import HttpServer
from opencoat_runtime_daemon.ipc.jsonrpc_dispatch import JsonRpcHandler
from opencoat_runtime_host_sdk import Client, ExtractionOutcome, ExtractionRejection
from opencoat_runtime_host_sdk.transport.http import (
    HostTransportCallError,
    HttpTransport,
)
from opencoat_runtime_host_sdk.transport.inproc import InProcTransport
from opencoat_runtime_protocol import Concern
from opencoat_runtime_storage.memory import MemoryConcernStore, MemoryDCNStore


def _runtime_with_scripted_llm(structured: dict[str, object]) -> OpenCOATRuntime:
    return OpenCOATRuntime(
        concern_store=MemoryConcernStore(),
        dcn_store=MemoryDCNStore(),
        llm=StubLLMClient(default_structured=structured),
    )


@pytest.fixture
def runtime() -> OpenCOATRuntime:
    return _runtime_with_scripted_llm({"name": "be brief"})


@pytest.fixture
def http_server(runtime: OpenCOATRuntime) -> Iterator[HttpServer]:
    rpc = JsonRpcHandler(runtime)
    srv = HttpServer(rpc, host="127.0.0.1", port=0, path="/rpc")
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.05)
    try:
        yield srv
    finally:
        srv.shutdown()
        thread.join(timeout=5)
        srv.server_close()


# ---------------------------------------------------------------------------
# Outcome shape contracts (independent of transport)
# ---------------------------------------------------------------------------


class TestExtractionOutcomeShape:
    def test_outcome_is_immutable(self) -> None:
        # Frozen dataclass — guards against accidental mutation of
        # the returned tuple in caller code.
        outcome = ExtractionOutcome(candidates=(), rejected=(), upserted=False)
        with pytest.raises(Exception):
            outcome.upserted = True  # type: ignore[misc]

    def test_rejection_carries_span_and_reason(self) -> None:
        rej = ExtractionRejection(span="some long span text", reason="duplicate")
        assert rej.span == "some long span text"
        assert rej.reason == "duplicate"


# ---------------------------------------------------------------------------
# In-proc transport — embedded mode
# ---------------------------------------------------------------------------


class TestInProcExtract:
    """``Client.connect('inproc://')`` short-circuits to a local
    :class:`ConcernExtractor` over ``runtime.llm`` — no daemon needed.

    These tests live in the host SDK package on purpose: an in-proc
    smoke that *only* exercises the dispatcher would miss the
    Client-layer reshaping (raw dict → ``ExtractionOutcome``).
    """

    def test_happy_path_returns_outcome_and_upserts(self, runtime: OpenCOATRuntime) -> None:
        client = Client.connect("inproc://", runtime=runtime)
        assert isinstance(client.transport, InProcTransport)

        outcome = client.extract_concerns(
            "Please keep every reply under three sentences.",
            origin="user_input",
            ref="prompt-42",
        )
        assert isinstance(outcome, ExtractionOutcome)
        assert outcome.upserted is True
        assert len(outcome.candidates) == 1
        c = outcome.candidates[0]
        assert isinstance(c, Concern)
        assert c.name == "be brief"
        assert c.source is not None
        assert c.source.origin == "user_input"
        assert c.source.ref == "prompt-42"
        # The candidate must be visible to the concern store after
        # the call — that's the headline value prop.
        assert runtime.concern_store.get(c.id) is not None

    def test_dry_run_does_not_upsert(self, runtime: OpenCOATRuntime) -> None:
        client = Client.connect("inproc://", runtime=runtime)
        outcome = client.extract_concerns(
            "Please keep every reply under three sentences.",
            origin="user_input",
            dry_run=True,
        )
        assert outcome.upserted is False
        assert len(outcome.candidates) == 1
        cid = outcome.candidates[0].id
        # Same id must not be visible from the store — that's the
        # contract.
        assert runtime.concern_store.get(cid) is None

    def test_unknown_origin_raises_value_error(self, runtime: OpenCOATRuntime) -> None:
        client = Client.connect("inproc://", runtime=runtime)
        with pytest.raises(ValueError, match=r"unsupported origin 'memory'"):
            client.extract_concerns("long enough text here", origin="memory")

    def test_blank_text_raises_value_error(self, runtime: OpenCOATRuntime) -> None:
        client = Client.connect("inproc://", runtime=runtime)
        with pytest.raises(ValueError, match=r"text must be a non-empty string"):
            client.extract_concerns("   ", origin="user_input")

    def test_no_candidates_when_llm_returns_empty(self) -> None:
        # Stub returns ``{}`` → extractor reads "no rule here". No
        # candidates, no rejections, no upsert side-effect.
        rt = _runtime_with_scripted_llm({})
        client = Client.connect("inproc://", runtime=rt)
        outcome = client.extract_concerns(
            "A plain prose paragraph that doesn't carry any rule.",
            origin="manual_import",
        )
        assert outcome.candidates == ()
        assert outcome.rejected == ()


# ---------------------------------------------------------------------------
# HTTP transport — the daemon path
# ---------------------------------------------------------------------------


class TestHttpExtract:
    """Same contract as :class:`TestInProcExtract`, exercised over the
    wire. Catches any regression in either the dispatcher's wire
    shape (``candidates`` / ``rejected`` / ``upserted`` keys) or the
    Client's reshape into :class:`ExtractionOutcome`.
    """

    def test_happy_path_round_trip(self, http_server: HttpServer, runtime: OpenCOATRuntime) -> None:
        base_url = f"http://{http_server.host}:{http_server.port}"
        client = Client.connect(base_url)
        assert isinstance(client.transport, HttpTransport)

        outcome = client.extract_concerns(
            "Please keep every reply under three sentences.",
            origin="user_input",
            ref="prompt-42",
        )
        assert outcome.upserted is True
        assert len(outcome.candidates) == 1
        # The wire side-effect must be visible from a parallel handle
        # to the same runtime — proves the daemon really upserted.
        cid = outcome.candidates[0].id
        assert runtime.concern_store.get(cid) is not None

    def test_dry_run_round_trip(self, http_server: HttpServer, runtime: OpenCOATRuntime) -> None:
        base_url = f"http://{http_server.host}:{http_server.port}"
        client = Client.connect(base_url)
        outcome = client.extract_concerns(
            "Please keep every reply under three sentences.",
            origin="user_input",
            dry_run=True,
        )
        assert outcome.upserted is False
        assert len(outcome.candidates) == 1
        cid = outcome.candidates[0].id
        assert runtime.concern_store.get(cid) is None

    def test_unknown_origin_surfaces_as_call_error(self, http_server: HttpServer) -> None:
        # ``-32602 invalid params`` on the wire must come up as
        # :class:`HostTransportCallError` on the host so callers can
        # branch on it.
        base_url = f"http://{http_server.host}:{http_server.port}"
        client = Client.connect(base_url)
        with pytest.raises(HostTransportCallError) as exc:
            client.extract_concerns("long enough text here", origin="memory")
        assert exc.value.code == -32602
        assert "memory" in exc.value.message
        # The allowed catalog must be in the message so the user
        # knows how to fix the call.
        assert "user_input" in exc.value.message
