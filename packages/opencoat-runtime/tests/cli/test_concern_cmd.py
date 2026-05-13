"""Tests for ``opencoat concern list | show | import | export | diff`` (M4 PR-22)."""

from __future__ import annotations

import argparse
import json
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from opencoat_runtime_cli.commands import concern_cmd
from opencoat_runtime_daemon import build_runtime
from opencoat_runtime_daemon.config import load_config
from opencoat_runtime_daemon.ipc.http_server import HttpServer
from opencoat_runtime_daemon.ipc.jsonrpc_dispatch import JsonRpcHandler
from opencoat_runtime_protocol import (
    Advice,
    AdviceType,
    Concern,
    Pointcut,
    WeavingLevel,
    WeavingOperation,
    WeavingPolicy,
)
from opencoat_runtime_protocol.envelopes import PointcutMatch

# ----------------------------------------------------------------------
# fixtures
# ----------------------------------------------------------------------


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
        # seed two concerns so list/show/diff have something to chew on
        built.runtime.concern_store.upsert(_concern("c-1", name="first"))
        built.runtime.concern_store.upsert(_concern("c-2", name="second"))
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
        "action": "list",
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
        # ``extract`` flags — kept in the defaults so every other
        # action test still constructs a complete Namespace.
        "demo": False,
        "from_text": None,
        "from_file": None,
        "origin": "user_input",
        "ref": None,
        "dry_run": False,
    }
    defaults.update(kw)
    return argparse.Namespace(**defaults)


# ----------------------------------------------------------------------
# list
# ----------------------------------------------------------------------


def test_list_default_prints_columns(
    in_proc_server: HttpServer, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = concern_cmd._handle(_ns(in_proc_server, action="list"))
    out = capsys.readouterr().out
    assert rc == 0
    assert "c-1" in out
    assert "c-2" in out
    assert "first" in out


def test_list_empty_says_so(in_proc_server: HttpServer, capsys: pytest.CaptureFixture[str]) -> None:
    rc = concern_cmd._handle(_ns(in_proc_server, action="list", lifecycle_state="archived"))
    out = capsys.readouterr().out
    assert rc == 0
    assert "(no concerns)" in out


def test_list_json_emits_array(
    in_proc_server: HttpServer, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = concern_cmd._handle(_ns(in_proc_server, action="list", json=True))
    out = capsys.readouterr().out
    assert rc == 0
    data = json.loads(out)
    assert isinstance(data, list)
    assert {c["id"] for c in data} == {"c-1", "c-2"}


def test_list_daemon_unreachable_returns_three(capsys: pytest.CaptureFixture[str]) -> None:
    ns = argparse.Namespace(
        action="list",
        target=None,
        target_b=None,
        config=None,
        host="127.0.0.1",
        port=1,
        path="/rpc",
        kind=None,
        tag=None,
        lifecycle_state=None,
        limit=None,
        json=False,
        output=None,
    )
    rc = concern_cmd._handle(ns)
    assert rc == 3
    assert "not reachable" in capsys.readouterr().err


# ----------------------------------------------------------------------
# show
# ----------------------------------------------------------------------


def test_show_returns_pretty_json(
    in_proc_server: HttpServer, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = concern_cmd._handle(_ns(in_proc_server, action="show", target="c-1"))
    out = capsys.readouterr().out
    assert rc == 0
    parsed = json.loads(out)
    assert parsed["id"] == "c-1"
    assert parsed["name"] == "first"


def test_show_missing_concern_exits_one(
    in_proc_server: HttpServer, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = concern_cmd._handle(_ns(in_proc_server, action="show", target="missing"))
    err = capsys.readouterr().err
    assert rc == 1
    assert "no concern" in err


def test_show_without_target_returns_two(
    in_proc_server: HttpServer, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = concern_cmd._handle(_ns(in_proc_server, action="show"))
    assert rc == 2
    assert "concern_id" in capsys.readouterr().err


# ----------------------------------------------------------------------
# import
# ----------------------------------------------------------------------


def test_import_round_trip_via_export(
    in_proc_server: HttpServer, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # 1. export the seed concerns to JSON …
    out_path = tmp_path / "concerns.json"
    rc = concern_cmd._handle(_ns(in_proc_server, action="export", output=str(out_path)))
    capsys.readouterr()
    assert rc == 0
    assert out_path.exists()

    # 2. tweak one and re-import the file → upsert should swallow it.
    data = json.loads(out_path.read_text())
    data[0]["name"] = "first-renamed"
    out_path.write_text(json.dumps(data))

    rc = concern_cmd._handle(_ns(in_proc_server, action="import", target=str(out_path)))
    out = capsys.readouterr().out
    assert rc == 0
    assert "upserted" in out
    assert "c-1" in out and "c-2" in out

    # 3. show confirms the rename took.
    rc = concern_cmd._handle(_ns(in_proc_server, action="show", target="c-1"))
    body = json.loads(capsys.readouterr().out)
    assert body["name"] == "first-renamed"


def test_import_rejects_garbage_yaml(
    in_proc_server: HttpServer, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("- not\n- a\n- mapping\n")
    rc = concern_cmd._handle(_ns(in_proc_server, action="import", target=str(bad)))
    err = capsys.readouterr().err
    assert rc == 2
    assert "list entries must be objects" in err


def test_import_without_target_returns_two(
    in_proc_server: HttpServer, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = concern_cmd._handle(_ns(in_proc_server, action="import"))
    assert rc == 2
    assert "<path>" in capsys.readouterr().err


# ----------------------------------------------------------------------
# export
# ----------------------------------------------------------------------


def test_export_to_stdout_emits_array(
    in_proc_server: HttpServer, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = concern_cmd._handle(_ns(in_proc_server, action="export"))
    out = capsys.readouterr().out
    assert rc == 0
    assert json.loads(out)


def test_export_with_target_emits_singleton(
    in_proc_server: HttpServer, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "one.json"
    rc = concern_cmd._handle(_ns(in_proc_server, action="export", target="c-1", output=str(target)))
    capsys.readouterr()
    assert rc == 0
    data = json.loads(target.read_text())
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["id"] == "c-1"


def test_export_missing_target_returns_one(
    in_proc_server: HttpServer, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = concern_cmd._handle(_ns(in_proc_server, action="export", target="missing"))
    assert rc == 1
    assert "no concern" in capsys.readouterr().err


# ----------------------------------------------------------------------
# diff
# ----------------------------------------------------------------------


def test_diff_returns_unified_diff(
    in_proc_server: HttpServer, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = concern_cmd._handle(_ns(in_proc_server, action="diff", target="c-1", target_b="c-2"))
    out = capsys.readouterr().out
    assert rc == 0
    assert "--- c-1" in out
    assert "+++ c-2" in out
    assert '"id": "c-1"' in out
    assert '"id": "c-2"' in out


def test_diff_against_self_is_clean(
    in_proc_server: HttpServer, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = concern_cmd._handle(_ns(in_proc_server, action="diff", target="c-1", target_b="c-1"))
    out = capsys.readouterr().out
    assert rc == 0
    assert "no diff" in out


def test_diff_missing_arg_returns_two(
    in_proc_server: HttpServer, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = concern_cmd._handle(_ns(in_proc_server, action="diff", target="c-1"))
    assert rc == 2
    assert "<a> <b>" in capsys.readouterr().err


def test_diff_missing_concern_returns_one(
    in_proc_server: HttpServer, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = concern_cmd._handle(_ns(in_proc_server, action="diff", target="c-1", target_b="nope"))
    err = capsys.readouterr().err
    assert rc == 1
    assert "missing concern(s)" in err


# ----------------------------------------------------------------------
# extract  (M5 PR-48)
# ----------------------------------------------------------------------


@pytest.fixture
def extract_server() -> Iterator[HttpServer]:
    """Server whose runtime has a scripted LLM so ``concern.extract``
    actually returns a candidate (instead of the empty-dict no-rule
    signal the default stub emits).
    """
    from opencoat_runtime_core import OpenCOATRuntime
    from opencoat_runtime_core.llm import StubLLMClient
    from opencoat_runtime_storage.memory import MemoryConcernStore, MemoryDCNStore

    rt = OpenCOATRuntime(
        concern_store=MemoryConcernStore(),
        dcn_store=MemoryDCNStore(),
        llm=StubLLMClient(default_structured={"name": "be brief"}),
    )
    rpc = JsonRpcHandler(rt)
    srv = HttpServer(rpc, host="127.0.0.1", port=0, path="/rpc")
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    time.sleep(0.05)
    try:
        # Surface the runtime so tests can inspect store side-effects.
        srv._test_runtime = rt  # type: ignore[attr-defined]
        yield srv
    finally:
        srv.shutdown()
        t.join(timeout=5)
        srv.server_close()


def test_extract_from_text_human_output(
    extract_server: HttpServer, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = concern_cmd._handle(
        _ns(
            extract_server,
            action="extract",
            from_text="Please keep every reply under three sentences.",
            origin="user_input",
        )
    )
    out = capsys.readouterr().out
    assert rc == 0
    # The summary line must carry origin + counts + side-effect label.
    assert "origin=user_input" in out
    assert "1 candidate" in out
    assert "upserted" in out
    # And the candidate line must show the new name.
    assert "be brief" in out
    # Side-effect: the candidate is now in the store.
    rt = extract_server._test_runtime  # type: ignore[attr-defined]
    assert sum(1 for _ in rt.concern_store.iter_all()) == 1


def test_extract_dry_run_does_not_upsert(
    extract_server: HttpServer, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = concern_cmd._handle(
        _ns(
            extract_server,
            action="extract",
            from_text="Please keep every reply under three sentences.",
            origin="user_input",
            dry_run=True,
        )
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "dry-run (not stored)" in out
    rt = extract_server._test_runtime  # type: ignore[attr-defined]
    assert sum(1 for _ in rt.concern_store.iter_all()) == 0


def test_extract_json_emits_full_wire(
    extract_server: HttpServer, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = concern_cmd._handle(
        _ns(
            extract_server,
            action="extract",
            from_text="Please keep every reply under three sentences.",
            origin="user_input",
            json=True,
        )
    )
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    # JSON mode must surface the daemon's exact wire shape so users
    # can pipe into ``jq``.
    assert set(payload) >= {"candidates", "rejected", "upserted"}
    assert len(payload["candidates"]) == 1
    assert payload["upserted"] is True


def test_extract_from_file(
    extract_server: HttpServer, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    p = tmp_path / "policy.md"
    p.write_text("1. Always reply in English regardless of input language.\n")
    rc = concern_cmd._handle(
        _ns(
            extract_server,
            action="extract",
            from_file=str(p),
            origin="manual_import",
        )
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "1 candidate" in out


def test_extract_from_text_and_file_is_misuse(
    extract_server: HttpServer, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = concern_cmd._handle(
        _ns(
            extract_server,
            action="extract",
            from_text="x",
            from_file="/tmp/anything",
        )
    )
    err = capsys.readouterr().err
    assert rc == 2
    assert "mutually exclusive" in err


def test_extract_empty_from_text_is_misuse(
    extract_server: HttpServer, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = concern_cmd._handle(
        _ns(extract_server, action="extract", from_text="   ", origin="user_input")
    )
    err = capsys.readouterr().err
    assert rc == 2
    assert "--from-text was empty" in err


def test_extract_unreadable_file_is_misuse(
    extract_server: HttpServer, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = concern_cmd._handle(
        _ns(
            extract_server,
            action="extract",
            from_file=str(tmp_path / "does-not-exist.md"),
        )
    )
    err = capsys.readouterr().err
    assert rc == 2
    assert "cannot read" in err


def test_extract_daemon_unreachable_returns_three(
    capsys: pytest.CaptureFixture[str],
) -> None:
    ns = argparse.Namespace(
        action="extract",
        target=None,
        target_b=None,
        config=None,
        host="127.0.0.1",
        port=1,
        path="/rpc",
        kind=None,
        tag=None,
        lifecycle_state=None,
        limit=None,
        json=False,
        output=None,
        demo=False,
        from_text="some text long enough to extract",
        from_file=None,
        origin="user_input",
        ref=None,
        dry_run=False,
    )
    rc = concern_cmd._handle(ns)
    assert rc == 3
    assert "not reachable" in capsys.readouterr().err


def test_extract_no_candidates_when_llm_returns_empty(
    in_proc_server: HttpServer, capsys: pytest.CaptureFixture[str]
) -> None:
    # ``in_proc_server`` uses the default builder which gives a stub
    # LLM returning ``{}`` (no rule). The CLI must report "(no
    # rule-shaped spans detected)" rather than crash.
    rc = concern_cmd._handle(
        _ns(
            in_proc_server,
            action="extract",
            from_text="Some innocuous prose that isn't a rule.",
            origin="manual_import",
        )
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "0 candidate(s)" in out
    assert "no rule-shaped spans detected" in out
