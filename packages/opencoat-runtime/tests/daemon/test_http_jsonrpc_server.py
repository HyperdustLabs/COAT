"""Tests for stdlib :class:`~opencoat_runtime_daemon.ipc.http_server.HttpServer` (M4 PR-19)."""

from __future__ import annotations

import json
import threading
import time
from http import HTTPStatus
from http.client import HTTPConnection

import pytest
from opencoat_runtime_daemon import build_runtime
from opencoat_runtime_daemon.config import load_config
from opencoat_runtime_daemon.ipc.http_server import HttpServer
from opencoat_runtime_daemon.ipc.jsonrpc_dispatch import JsonRpcHandler


def _post_json(
    conn: HTTPConnection,
    path: str,
    payload: object,
    *,
    extra_headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Content-Length": str(len(body)),
    }
    if extra_headers:
        headers.update(extra_headers)
    conn.request("POST", path, body=body, headers=headers)
    resp = conn.getresponse()
    raw = resp.read()
    hdrs = {k.lower(): v for k, v in resp.headers.items()}
    return resp.status, hdrs, raw


@pytest.fixture
def http_server() -> HttpServer:
    with build_runtime(load_config(), env={}) as built:
        rpc = JsonRpcHandler(built.runtime)
        srv = HttpServer(rpc, host="127.0.0.1", port=0, path="/rpc")
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        time.sleep(0.05)
        try:
            yield srv
        finally:
            srv.shutdown()
            t.join(timeout=5)
            srv.server_close()


def test_health_ping_200(http_server: HttpServer) -> None:
    conn = HTTPConnection(http_server.host, http_server.port, timeout=5)
    try:
        status, hdrs, raw = _post_json(
            conn,
            "/rpc",
            {"jsonrpc": "2.0", "id": 1, "method": "health.ping"},
        )
        assert status == HTTPStatus.OK
        assert "application/json" in hdrs.get("content-type", "")
        data = json.loads(raw.decode())
        assert data == {"jsonrpc": "2.0", "result": {"ok": True}, "id": 1}
    finally:
        conn.close()


def test_notification_204(http_server: HttpServer) -> None:
    conn = HTTPConnection(http_server.host, http_server.port, timeout=5)
    try:
        status, _hdrs, raw = _post_json(
            conn,
            "/rpc",
            {"jsonrpc": "2.0", "method": "health.ping"},
        )
        assert status == HTTPStatus.NO_CONTENT
        assert raw == b""
    finally:
        conn.close()


def test_get_rpc_path_405_with_allow_post(http_server: HttpServer) -> None:
    conn = HTTPConnection(http_server.host, http_server.port, timeout=5)
    try:
        conn.request("GET", "/rpc")
        resp = conn.getresponse()
        assert resp.status == HTTPStatus.METHOD_NOT_ALLOWED
        assert resp.getheader("Allow") == "POST"
        resp.read()
    finally:
        conn.close()


def test_post_wrong_path_404(http_server: HttpServer) -> None:
    conn = HTTPConnection(http_server.host, http_server.port, timeout=5)
    try:
        status, _hdrs, _raw = _post_json(
            conn,
            "/nope",
            {"jsonrpc": "2.0", "id": 1, "method": "health.ping"},
        )
        assert status == HTTPStatus.NOT_FOUND
    finally:
        conn.close()


def test_trailing_slash_matches_normalized_path(http_server: HttpServer) -> None:
    conn = HTTPConnection(http_server.host, http_server.port, timeout=5)
    try:
        status, _hdrs, raw = _post_json(
            conn,
            "/rpc/",
            {"jsonrpc": "2.0", "id": 7, "method": "health.ping"},
        )
        assert status == HTTPStatus.OK
        assert json.loads(raw.decode())["id"] == 7
    finally:
        conn.close()


def test_invalid_content_length_400(http_server: HttpServer) -> None:
    conn = HTTPConnection(http_server.host, http_server.port, timeout=5)
    try:
        conn.request(
            "POST",
            "/rpc",
            body=b"{}",
            headers={"Content-Type": "application/json", "Content-Length": "not-a-number"},
        )
        resp = conn.getresponse()
        assert resp.status == HTTPStatus.BAD_REQUEST
        resp.read()
    finally:
        conn.close()


def test_custom_rpc_path() -> None:
    with build_runtime(load_config(), env={}) as built:
        rpc = JsonRpcHandler(built.runtime)
        srv = HttpServer(rpc, host="127.0.0.1", port=0, path="/v1/opencoat")
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        time.sleep(0.05)
        conn = HTTPConnection(srv.host, srv.port, timeout=5)
        try:
            status, _hdrs, raw = _post_json(
                conn,
                "/v1/opencoat",
                {"jsonrpc": "2.0", "id": 1, "method": "health.ping"},
            )
            assert status == HTTPStatus.OK
            assert json.loads(raw.decode())["result"]["ok"] is True
        finally:
            conn.close()
            srv.shutdown()
            t.join(timeout=5)
            srv.server_close()
