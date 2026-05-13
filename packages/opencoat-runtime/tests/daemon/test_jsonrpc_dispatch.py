"""Tests for :class:`~opencoat_runtime_daemon.ipc.jsonrpc_dispatch.JsonRpcHandler` (M4 PR-18)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from opencoat_runtime_daemon import build_runtime
from opencoat_runtime_daemon.config import load_config
from opencoat_runtime_daemon.ipc.jsonrpc_dispatch import JsonRpcHandler
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


class TestJsonRpcCompliance:
    """Codex P2 on PR-18: response id + validation error mapping."""

    def test_validation_error_maps_to_invalid_params(self, handler: JsonRpcHandler) -> None:
        # ``joinpoint`` is shaped right but fails Pydantic validation
        # (missing required fields). Must be -32602, not -32603.
        out = handler.handle(
            _req("joinpoint.submit", {"joinpoint": {"id": "jp-bad"}}),
        )
        assert out is not None
        assert out["error"]["code"] == -32602
        assert "validation" in out["error"]["message"].lower()

    def test_concern_upsert_validation_error_is_invalid_params(
        self, handler: JsonRpcHandler
    ) -> None:
        out = handler.handle(_req("concern.upsert", {"concern": {"id": "broken"}}))
        assert out is not None
        assert out["error"]["code"] == -32602

    def test_notification_returns_none(self, handler: JsonRpcHandler) -> None:
        # JSON-RPC 2.0 §4.1: request without "id" is a notification;
        # server MUST NOT reply. We return None so the HTTP layer can
        # translate that into 204/no body.
        assert handler.handle({"jsonrpc": "2.0", "method": "health.ping"}) is None

    def test_notification_with_invalid_method_still_returns_none(
        self, handler: JsonRpcHandler
    ) -> None:
        assert handler.handle({"jsonrpc": "2.0", "method": "nope.bad"}) is None

    def test_response_always_contains_id_member(self, handler: JsonRpcHandler) -> None:
        out = handler.handle(_req("health.ping", req_id=42))
        assert out is not None
        assert "id" in out and out["id"] == 42

    def test_explicit_null_id_is_a_real_request_not_a_notification(
        self, handler: JsonRpcHandler
    ) -> None:
        # JSON-RPC 2.0: ``"id": null`` is a real request; the
        # response must echo it back. Only an *omitted* id makes
        # the message a notification.
        out = handler.handle({"jsonrpc": "2.0", "method": "health.ping", "id": None})
        assert out is not None
        assert out["id"] is None
        assert out["result"] == {"ok": True}

    def test_parse_error_response_has_id_null(self, handler: JsonRpcHandler) -> None:
        out = handler.handle("not json")
        assert out is not None
        assert out["error"]["code"] == -32700
        assert out["id"] is None


class TestInvalidEnvelopeStillResponds:
    """Codex P2 on PR-19: invalid Request objects without ``id`` must
    still receive an error response with ``id: null`` — only *valid*
    Request objects without ``id`` are JSON-RPC notifications (§4.1).
    """

    def test_bad_jsonrpc_version_without_id_returns_error(self, handler: JsonRpcHandler) -> None:
        out = handler.handle({"jsonrpc": "1.0", "method": "health.ping"})
        assert out is not None
        assert out["error"]["code"] == -32600
        assert out["id"] is None

    def test_method_not_string_without_id_returns_error(self, handler: JsonRpcHandler) -> None:
        out = handler.handle({"jsonrpc": "2.0", "method": 1})
        assert out is not None
        assert out["error"]["code"] == -32600
        assert out["id"] is None

    def test_missing_method_without_id_returns_error(self, handler: JsonRpcHandler) -> None:
        out = handler.handle({"jsonrpc": "2.0"})
        assert out is not None
        assert out["error"]["code"] == -32600
        assert out["id"] is None

    def test_bad_params_type_without_id_returns_error(self, handler: JsonRpcHandler) -> None:
        out = handler.handle({"jsonrpc": "2.0", "method": "health.ping", "params": "hello"})
        assert out is not None
        assert out["error"]["code"] == -32602
        assert out["id"] is None

    def test_unknown_method_with_id_still_returns_error(self, handler: JsonRpcHandler) -> None:
        # Sanity: well-formed envelope, unknown method, id present →
        # -32601 with that id (suppression only fires on notifications).
        out = handler.handle({"jsonrpc": "2.0", "method": "no.such.method", "id": 5})
        assert out is not None
        assert out["error"]["code"] == -32601
        assert out["id"] == 5
