"""Tests for ``COATr dcn`` (M4 PR-22)."""

from __future__ import annotations

import argparse
import json
import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from COAT_runtime_cli.commands import dcn_cmd
from COAT_runtime_daemon import build_runtime
from COAT_runtime_daemon.config import load_config
from COAT_runtime_daemon.ipc.http_server import HttpServer
from COAT_runtime_daemon.ipc.jsonrpc_dispatch import JsonRpcHandler
from COAT_runtime_protocol import (
    Advice,
    AdviceType,
    Concern,
    Pointcut,
    WeavingLevel,
    WeavingOperation,
    WeavingPolicy,
)
from COAT_runtime_protocol.envelopes import PointcutMatch


def _concern(cid: str, name: str = "demo") -> Concern:
    return Concern(
        id=cid,
        name=name,
        description="d",
        pointcut=Pointcut(match=PointcutMatch(any_keywords=["refund"])),
        advice=Advice(type=AdviceType.REASONING_GUIDANCE, content="hint"),
        weaving_policy=WeavingPolicy(
            mode=WeavingOperation.INSERT,
            level=WeavingLevel.PROMPT_LEVEL,
            target="reasoning.hints",
            priority=0.5,
        ),
    )


@pytest.fixture
def in_proc_server() -> Iterator[HttpServer]:
    with build_runtime(load_config(), env={}) as built:
        rt = built.runtime
        rt.concern_store.upsert(_concern("c-1", "rule-one"))
        rt.concern_store.upsert(_concern("c-2", "rule-two"))
        # Mirror nodes into the DCN store so activation logging is valid.
        rt.dcn_store.add_node(rt.concern_store.get("c-1"))
        rt.dcn_store.add_node(rt.concern_store.get("c-2"))
        ts = datetime(2026, 5, 11, 14, tzinfo=UTC)
        rt.dcn_store.log_activation("c-1", "before_response", 0.9, ts)
        rt.dcn_store.log_activation("c-2", "before_response", 0.7, ts)
        rt.dcn_store.log_activation("c-1", "after_response", 0.5, ts)

        rpc = JsonRpcHandler(rt)
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


def _ns(server: HttpServer | None = None, **kw: object) -> argparse.Namespace:
    defaults: dict[str, object] = {
        "action": "export",
        "config": None,
        "host": server.host if server else "127.0.0.1",
        "port": server.port if server else 1,
        "path": "/rpc",
        "format": "json",
        "output": None,
        "concern_id": None,
        "limit": None,
        "json": False,
    }
    defaults.update(kw)
    return argparse.Namespace(**defaults)


# ----------------------------------------------------------------------
# activation-log
# ----------------------------------------------------------------------


def test_activation_log_default_columns(
    in_proc_server: HttpServer, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = dcn_cmd._handle(_ns(in_proc_server, action="activation-log"))
    out = capsys.readouterr().out
    assert rc == 0
    assert "before_response" in out
    assert "after_response" in out
    assert "c-1" in out and "c-2" in out


def test_activation_log_filters_by_concern(
    in_proc_server: HttpServer, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = dcn_cmd._handle(_ns(in_proc_server, action="activation-log", concern_id="c-2"))
    out = capsys.readouterr().out
    assert rc == 0
    assert "c-2" in out
    assert "c-1" not in out


def test_activation_log_json_emits_array(
    in_proc_server: HttpServer, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = dcn_cmd._handle(_ns(in_proc_server, action="activation-log", json=True))
    rows = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert isinstance(rows, list)
    assert len(rows) == 3


def test_activation_log_empty_is_handled(
    in_proc_server: HttpServer, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = dcn_cmd._handle(_ns(in_proc_server, action="activation-log", concern_id="ghost"))
    out = capsys.readouterr().out
    assert rc == 0
    assert "(no activations)" in out


def test_activation_log_daemon_unreachable_returns_three(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = dcn_cmd._handle(_ns(action="activation-log"))
    err = capsys.readouterr().err
    assert rc == 3
    assert "not reachable" in err


# ----------------------------------------------------------------------
# export
# ----------------------------------------------------------------------


def test_export_json_to_stdout(
    in_proc_server: HttpServer, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = dcn_cmd._handle(_ns(in_proc_server, action="export", format="json"))
    out = capsys.readouterr().out
    assert rc == 0
    snap = json.loads(out)
    assert {c["id"] for c in snap["concerns"]} == {"c-1", "c-2"}
    assert len(snap["activation_log"]) == 3


def test_export_dot_to_file(
    in_proc_server: HttpServer, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "dcn.dot"
    rc = dcn_cmd._handle(_ns(in_proc_server, action="export", format="dot", output=str(target)))
    assert rc == 0
    text = target.read_text()
    assert text.startswith("digraph DCN")
    assert "rule-one" in text
    assert "before_response" in text
    err = capsys.readouterr().err
    # Friendly summary lands on stderr so stdout stays empty for piping.
    assert "wrote 2 concern" in err


def test_export_unknown_format_returns_two(
    in_proc_server: HttpServer, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = dcn_cmd._handle(_ns(in_proc_server, action="export", format="png"))
    assert rc == 2
    assert "unsupported" in capsys.readouterr().err


# ----------------------------------------------------------------------
# visualize (alias)
# ----------------------------------------------------------------------


def test_visualize_emits_dot_to_stdout(
    in_proc_server: HttpServer, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = dcn_cmd._handle(_ns(in_proc_server, action="visualize"))
    out = capsys.readouterr().out
    assert rc == 0
    assert "digraph DCN" in out
    assert "->" in out  # at least one edge


# ----------------------------------------------------------------------
# import (deferred)
# ----------------------------------------------------------------------


def test_import_is_deferred_with_clean_error(capsys: pytest.CaptureFixture[str]) -> None:
    rc = dcn_cmd._handle(_ns(action="import"))
    err = capsys.readouterr().err
    assert rc == 2
    assert "not yet implemented" in err
