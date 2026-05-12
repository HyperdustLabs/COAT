"""Tests for ``COATr concern import --demo`` (DX sprint #3)."""

from __future__ import annotations

import argparse
import json
import threading
import time
from collections.abc import Iterator

import pytest
from COAT_runtime_cli.commands import concern_cmd
from COAT_runtime_cli.demo_concerns import (
    DEMO_MEMORY_TAG_ID,
    DEMO_PROMPT_PREFIX_ID,
    DEMO_TOOL_BLOCK_ID,
    demo_concerns,
)
from COAT_runtime_daemon import build_runtime
from COAT_runtime_daemon.config import load_config
from COAT_runtime_daemon.ipc.http_server import HttpServer
from COAT_runtime_daemon.ipc.jsonrpc_dispatch import JsonRpcHandler
from COAT_runtime_protocol import AdviceType, WeavingOperation

EXPECTED_IDS = {DEMO_PROMPT_PREFIX_ID, DEMO_TOOL_BLOCK_ID, DEMO_MEMORY_TAG_ID}


# ----------------------------------------------------------------------
# Pure unit-level invariants — no daemon needed
# ----------------------------------------------------------------------


class TestDemoConcernsShape:
    def test_three_unique_ids(self) -> None:
        ids = [c.id for c in demo_concerns()]
        assert set(ids) == EXPECTED_IDS
        assert len(ids) == len(set(ids)), "demo set has duplicate ids"

    def test_one_concern_per_advicetype(self) -> None:
        """Each demo concern demonstrates a distinct AdviceType lane."""
        by_advice = {c.advice.type for c in demo_concerns() if c.advice is not None}
        assert by_advice == {
            AdviceType.RESPONSE_REQUIREMENT,
            AdviceType.TOOL_GUARD,
            AdviceType.MEMORY_WRITE_GUARD,
        }

    def test_tool_block_uses_block_mode(self) -> None:
        """``demo-tool-block`` must be BLOCK so the M5 tool_guard fires."""
        tool_block = next(c for c in demo_concerns() if c.id == DEMO_TOOL_BLOCK_ID)
        assert tool_block.weaving_policy is not None
        assert tool_block.weaving_policy.mode == WeavingOperation.BLOCK
        assert tool_block.weaving_policy.target.startswith("tool_call.arguments")

    def test_joinpoints_are_reachable_via_openclaw_adapter(self) -> None:
        """Every demo concern's joinpoint must be emitted by the OpenClaw adapter.

        Pins the lesson from Codex P2 on PR #37 (`on_request_received`
        unreachable) so the demo set cannot silently drift off-catalog.
        """
        from COAT_runtime_host_openclaw.joinpoint_map import OPENCLAW_EVENT_MAP

        emitted = set(OPENCLAW_EVENT_MAP.values())
        for c in demo_concerns():
            assert c.pointcut is not None
            for jp in c.pointcut.joinpoints:
                assert jp in emitted, (
                    f"demo concern {c.id!r} uses joinpoint {jp!r} which "
                    f"OpenClawAdapter never emits (catalog: {sorted(emitted)})"
                )


# ----------------------------------------------------------------------
# Round-trip through the daemon
# ----------------------------------------------------------------------


@pytest.fixture
def in_proc_server() -> Iterator[HttpServer]:
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


def _ns(server: HttpServer, **kw: object) -> argparse.Namespace:
    defaults: dict[str, object] = {
        "action": "import",
        "target": None,
        "target_b": None,
        "config": None,
        "host": server.host,
        "port": server.port,
        "path": "/rpc",
        "kind": None,
        "tag": None,
        "lifecycle_state": None,
        "limit": None,
        "json": False,
        "output": None,
        "demo": False,
    }
    defaults.update(kw)
    return argparse.Namespace(**defaults)


class TestConcernImportDemo:
    def test_demo_flag_upserts_three_concerns(
        self, in_proc_server: HttpServer, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc = concern_cmd._handle(_ns(in_proc_server, action="import", demo=True))
        out = capsys.readouterr().out
        assert rc == 0
        assert "upserted 3 concern(s) from --demo set" in out
        for cid in EXPECTED_IDS:
            assert cid in out

    def test_demo_concerns_visible_via_list(
        self, in_proc_server: HttpServer, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc = concern_cmd._handle(_ns(in_proc_server, action="import", demo=True))
        assert rc == 0
        capsys.readouterr()

        rc = concern_cmd._handle(_ns(in_proc_server, action="list", json=True))
        listed = json.loads(capsys.readouterr().out)
        assert rc == 0
        listed_ids = {c["id"] for c in listed}
        assert EXPECTED_IDS.issubset(listed_ids)

    def test_demo_import_is_idempotent(self, in_proc_server: HttpServer) -> None:
        """Re-running ``--demo`` upserts the same ids — no duplicates."""
        rc1 = concern_cmd._handle(_ns(in_proc_server, action="import", demo=True))
        rc2 = concern_cmd._handle(_ns(in_proc_server, action="import", demo=True))
        assert rc1 == rc2 == 0

    def test_demo_flag_with_target_rejects(
        self, in_proc_server: HttpServer, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc = concern_cmd._handle(
            _ns(in_proc_server, action="import", demo=True, target="some-file.json")
        )
        err = capsys.readouterr().err
        assert rc == 2
        assert "mutually exclusive" in err

    def test_import_without_target_or_demo_still_two(
        self, in_proc_server: HttpServer, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc = concern_cmd._handle(_ns(in_proc_server, action="import"))
        err = capsys.readouterr().err
        assert rc == 2
        assert "--demo" in err
