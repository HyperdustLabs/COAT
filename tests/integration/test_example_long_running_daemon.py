"""Smoke + behavioural tests for ``examples/06_long_running_daemon``.

Pins M4 PR-23: a real :class:`COAT_runtime_daemon.Daemon` is started
on a free loopback port, then driven from the same
:class:`COAT_runtime_cli.transport.HttpRpcClient` that ``COATr concern``
/ ``COATr dcn`` ship. If anything in PR-17→PR-22 regresses on the wire
this test trips, with the example folder doubling as both the docs
artefact and the integration fixture.

Loaded via ``importlib`` because the folder name starts with a digit.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from COAT_runtime_cli.transport import HttpRpcClient
from COAT_runtime_daemon import Daemon

EXAMPLE_DIR = Path(__file__).resolve().parents[2] / "examples" / "06_long_running_daemon"
PKG_NAME = "_COAT_example_long_running_daemon"


def _load_example() -> tuple:
    """Return ``(main_mod, concerns_mod)``."""
    pkg_init = EXAMPLE_DIR / "__init__.py"
    if PKG_NAME not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            PKG_NAME,
            pkg_init,
            submodule_search_locations=[str(EXAMPLE_DIR)],
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[PKG_NAME] = module
        spec.loader.exec_module(module)

    for name in ("concerns", "main"):
        full = f"{PKG_NAME}.{name}"
        if full not in sys.modules:
            sub_spec = importlib.util.spec_from_file_location(full, EXAMPLE_DIR / f"{name}.py")
            assert sub_spec is not None and sub_spec.loader is not None
            mod = importlib.util.module_from_spec(sub_spec)
            sys.modules[full] = mod
            sub_spec.loader.exec_module(mod)

    return sys.modules[f"{PKG_NAME}.main"], sys.modules[f"{PKG_NAME}.concerns"]


@pytest.fixture(scope="module")
def example_modules() -> tuple:
    return _load_example()


@pytest.fixture
def running_daemon(example_modules, tmp_path: Path):
    main_mod, _ = example_modules
    port = main_mod._pick_free_port()
    config = main_mod._build_demo_config(port=port, state_db=None)
    daemon = Daemon(config, env={}, pid_file=tmp_path / "coat.pid")
    daemon.start()
    try:
        client = HttpRpcClient(host="127.0.0.1", port=port, path="/rpc", timeout=5.0)
        yield daemon, client, port
    finally:
        daemon.stop()


class TestProgrammaticTour:
    def test_run_tour_seeds_and_drives_joinpoints(
        self, example_modules, running_daemon, tmp_path: Path
    ) -> None:
        main_mod, _ = example_modules
        _, client, _ = running_daemon

        report = main_mod.run_tour(client, dot_out=tmp_path / "dcn.dot")

        assert report["health"] == {"ok": True}
        assert set(report["seeded"]) == {"c-concise", "c-cite", "c-no-pii"}
        # All three demo joinpoints match at least one concern.
        assert report["injection_matches"] == 3
        assert {c["id"] for c in report["concerns"]} == {"c-concise", "c-cite", "c-no-pii"}
        # Activation log has entries for every match × the keywords that
        # fired on it. Don't pin the exact count — the matcher is allowed
        # to score multiple concerns per joinpoint — just require the
        # PII concern fired on the email prompt.
        ids = {row["concern_id"] for row in report["activation_log"]}
        assert "c-no-pii" in ids
        # DOT output via PR-22's dcn_to_dot.
        dot_path = tmp_path / "dcn.dot"
        assert dot_path.exists()
        body = dot_path.read_text(encoding="utf-8")
        assert body.startswith("digraph DCN")
        assert '"c:c-no-pii"' in body
        assert '"j:jp-demo-3"' in body

    def test_seed_is_idempotent(self, example_modules, running_daemon) -> None:
        main_mod, _ = example_modules
        _, client, _ = running_daemon

        first = main_mod._seed_concerns_if_empty(client)
        second = main_mod._seed_concerns_if_empty(client)
        assert set(first) == {"c-concise", "c-cite", "c-no-pii"}
        assert second == []

    def test_runtime_snapshot_shape(self, example_modules, running_daemon) -> None:
        _, _ = example_modules
        _, client, _ = running_daemon

        snap = client.call("runtime.snapshot", {})
        assert isinstance(snap, dict)
        # Required shape `runtime status` (PR-21) and the demo's
        # `_format_snapshot` both lean on.
        assert "concern_count" in snap
        assert "active_concern_count" in snap


class TestCliEntry:
    def test_main_in_memory_returns_zero(self, example_modules, tmp_path: Path, capsys) -> None:
        main_mod, _ = example_modules
        rc = main_mod.main(
            argv=[
                "--in-memory",
                "--pid-file",
                str(tmp_path / "coat.pid"),
            ]
        )
        out = capsys.readouterr().out
        assert rc == 0
        assert "health.ping" in out
        assert "runtime.snapshot" in out
        assert "Done." in out

    def test_main_sqlite_persists_concerns_between_runs(
        self, example_modules, tmp_path: Path, capsys
    ) -> None:
        main_mod, _ = example_modules
        db = tmp_path / "state.db"
        pid = tmp_path / "coat.pid"

        rc1 = main_mod.main(argv=["--state-db", str(db), "--pid-file", str(pid)])
        out1 = capsys.readouterr().out
        assert rc1 == 0
        assert "seeded: c-concise, c-cite, c-no-pii" in out1
        assert db.exists()

        rc2 = main_mod.main(argv=["--state-db", str(db), "--pid-file", str(pid)])
        out2 = capsys.readouterr().out
        assert rc2 == 0
        # Second run finds the rows already present and skips seeding.
        assert "seeded: (none — sqlite already had them)" in out2

    def test_dot_output_written(self, example_modules, tmp_path: Path, capsys) -> None:
        main_mod, _ = example_modules
        out_dot = tmp_path / "dcn.dot"
        rc = main_mod.main(
            argv=[
                "--in-memory",
                "--pid-file",
                str(tmp_path / "coat.pid"),
                "--dot-out",
                str(out_dot),
            ]
        )
        capsys.readouterr()
        assert rc == 0
        assert out_dot.exists()
        body = out_dot.read_text(encoding="utf-8")
        assert body.startswith("digraph DCN")
        # Quoted ids from PR-22's collision-safe fix.
        assert '"c:c-concise"' in body
