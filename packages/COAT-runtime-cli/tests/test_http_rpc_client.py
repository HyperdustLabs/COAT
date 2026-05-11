"""Tests for :class:`~COAT_runtime_cli.transport.HttpRpcClient` (M4 PR-21)."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator

import pytest
from COAT_runtime_cli.transport import (
    HttpRpcCallError,
    HttpRpcClient,
    HttpRpcConnectionError,
    HttpRpcError,
    HttpRpcProtocolError,
)
from COAT_runtime_daemon import build_runtime
from COAT_runtime_daemon.config import load_config
from COAT_runtime_daemon.ipc.http_server import HttpServer
from COAT_runtime_daemon.ipc.jsonrpc_dispatch import JsonRpcHandler


@pytest.fixture
def running_server() -> Iterator[HttpServer]:
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


def test_call_returns_result(running_server: HttpServer) -> None:
    client = HttpRpcClient(host=running_server.host, port=running_server.port)
    result = client.call("health.ping")
    assert result == {"ok": True}


def test_call_unknown_method_raises_call_error(running_server: HttpServer) -> None:
    client = HttpRpcClient(host=running_server.host, port=running_server.port)
    with pytest.raises(HttpRpcCallError) as exc:
        client.call("does.not.exist")
    assert exc.value.code == -32601
    assert "does.not.exist" in exc.value.message


def test_call_invalid_params_raises_call_error(running_server: HttpServer) -> None:
    client = HttpRpcClient(host=running_server.host, port=running_server.port)
    with pytest.raises(HttpRpcCallError) as exc:
        client.call("concern.get", {"concern_id": 123})
    assert exc.value.code == -32602


def test_connection_refused_raises_connection_error() -> None:
    # Port 1 is privileged and never bound by an unprivileged listener.
    client = HttpRpcClient(host="127.0.0.1", port=1, timeout=0.5)
    with pytest.raises(HttpRpcConnectionError):
        client.call("health.ping")


def test_custom_path_and_endpoint() -> None:
    client = HttpRpcClient(host="example.invalid", port=9999, path="v2/rpc")
    assert client.path == "/v2/rpc"
    assert client.endpoint == "http://example.invalid:9999/v2/rpc"


def test_call_assigns_incrementing_request_ids(running_server: HttpServer) -> None:
    client = HttpRpcClient(host=running_server.host, port=running_server.port)
    assert client._next_id == 1
    client.call("health.ping")
    client.call("health.ping")
    assert client._next_id == 3


def test_call_rejects_empty_method() -> None:
    client = HttpRpcClient(host="127.0.0.1", port=1)
    with pytest.raises(ValueError, match="non-empty"):
        client.call("")


def test_error_hierarchy_collapses_to_base() -> None:
    # All concrete errors derive from HttpRpcError so callers can use a
    # single except clause without catching anything else.
    for cls in (HttpRpcConnectionError, HttpRpcProtocolError, HttpRpcCallError):
        assert issubclass(cls, HttpRpcError)
