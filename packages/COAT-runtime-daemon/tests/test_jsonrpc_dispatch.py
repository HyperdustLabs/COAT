"""Tests for :class:`~COAT_runtime_daemon.ipc.jsonrpc_dispatch.JsonRpcHandler` (M4 PR-18)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from COAT_runtime_daemon import build_runtime
from COAT_runtime_daemon.config import load_config
from COAT_runtime_daemon.ipc.jsonrpc_dispatch import JsonRpcHandler
from COAT_runtime_protocol import (
    Advice,
    AdviceType,
    Concern,
    JoinpointEvent,
    Pointcut,
    WeavingLevel,
    WeavingOperation,
    WeavingPolicy,
)
from COAT_runtime_protocol.envelopes import PointcutMatch


def _concern(cid: str = "c-rpc") -> Concern:
    return Concern(
        id=cid,
        name="RPC smoke",
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


def _jp() -> JoinpointEvent:
    return JoinpointEvent(
        id="jp-rpc",
        level=2,
        name="before_response",
        host="jsonrpc-test",
        agent_session_id="s",
        ts=datetime(2026, 5, 11, 14, 0, tzinfo=UTC),
        payload={"text": "refund", "raw_text": "refund"},
    )


@pytest.fixture
def handler() -> JsonRpcHandler:
    with build_runtime(load_config(), env={}) as built:
        yield JsonRpcHandler(built.runtime)


def _req(method: str, params: object | None = None, *, req_id: object = 1) -> dict:
    d: dict = {"jsonrpc": "2.0", "method": method, "id": req_id}
    if params is not None:
        d["params"] = params
    return d


class TestEnvelope:
    def test_parse_error(self, handler: JsonRpcHandler) -> None:
        out = handler.handle("{")
        assert out["error"]["code"] == -32700

    def test_invalid_not_object(self, handler: JsonRpcHandler) -> None:
        out = handler.handle("[1,2,3]")
        assert out["error"]["code"] == -32600

    def test_method_not_found(self, handler: JsonRpcHandler) -> None:
        out = handler.handle(_req("nope.missing"))
        assert out["error"]["code"] == -32601

    def test_bad_jsonrpc_version(self, handler: JsonRpcHandler) -> None:
        out = handler.handle({"jsonrpc": "1.0", "method": "health.ping", "id": 1})
        assert out["error"]["code"] == -32600


class TestMethods:
    def test_health_ping(self, handler: JsonRpcHandler) -> None:
        out = handler.handle(_req("health.ping"))
        assert out == {"jsonrpc": "2.0", "result": {"ok": True}, "id": 1}

    def test_round_trip_via_json_string(self, handler: JsonRpcHandler) -> None:
        c = _concern()
        h = handler
        up = h.handle(json.dumps(_req("concern.upsert", {"concern": c.model_dump(mode="json")})))
        assert "error" not in up
        assert up["result"]["id"] == "c-rpc"

        got = h.handle(json.dumps(_req("concern.get", {"concern_id": "c-rpc"})))
        assert got["result"]["id"] == "c-rpc"

        inj = h.handle(
            json.dumps(
                _req(
                    "joinpoint.submit",
                    {"joinpoint": _jp().model_dump(mode="json")},
                )
            )
        )
        assert "error" not in inj
        assert inj["result"] is not None
        assert any(x["concern_id"] == "c-rpc" for x in inj["result"]["injections"])

        snap = h.handle(_req("runtime.snapshot"))
        assert snap["result"]["concern_count"] >= 1

        h.handle(_req("concern.delete", {"concern_id": "c-rpc"}))
        gone = h.handle(_req("concern.get", {"concern_id": "c-rpc"}))
        assert gone["result"] is None

    def test_invalid_joinpoint_params(self, handler: JsonRpcHandler) -> None:
        out = handler.handle(_req("joinpoint.submit", {}))
        assert out["error"]["code"] == -32602

    def test_activation_log_empty(self, handler: JsonRpcHandler) -> None:
        out = handler.handle(_req("dcn.activation_log", {}))
        assert out["result"] == []
