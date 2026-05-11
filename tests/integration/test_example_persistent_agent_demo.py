"""Smoke + behavioural tests for ``examples/03_persistent_agent_demo``.

Pins M3 PR-16: sqlite ``ConcernStore`` + ``DCNStore`` on one file,
optional :class:`~COAT_runtime_storage.jsonl.SessionJsonlRecorder`, and
``replay_session_file`` against the written JSONL.

Loaded via ``importlib`` because the folder name starts with a digit.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from COAT_runtime_storage.jsonl import replay_session_file

EXAMPLE_DIR = Path(__file__).resolve().parents[2] / "examples" / "03_persistent_agent_demo"
PKG_NAME = "_COAT_example_persistent_agent_demo"


def _load_example() -> tuple:
    """Return ``(agent_mod, main_mod)``."""
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

    for name in ("agent", "main", "concerns"):
        full = f"{PKG_NAME}.{name}"
        if full not in sys.modules:
            sub_spec = importlib.util.spec_from_file_location(full, EXAMPLE_DIR / f"{name}.py")
            assert sub_spec is not None and sub_spec.loader is not None
            mod = importlib.util.module_from_spec(sub_spec)
            sys.modules[full] = mod
            sub_spec.loader.exec_module(mod)

    return sys.modules[f"{PKG_NAME}.agent"], sys.modules[f"{PKG_NAME}.main"]


@pytest.fixture(scope="module")
def example_modules() -> tuple:
    return _load_example()


class TestPersistentAgent:
    def test_sqlite_seeds_once_then_resumes(self, tmp_path: Path, example_modules) -> None:
        agent_mod, _ = example_modules
        db = tmp_path / "state.db"

        with agent_mod.PersistentAgent(db, session_jsonl=None) as a1:
            a1.handle("Who invented the COAT runtime?")
            ids1 = {c.id for c in a1.runtime.concern_store.iter_all()}
        assert ids1 == {"c-concise", "c-cite", "c-no-pii"}

        with agent_mod.PersistentAgent(db, session_jsonl=None) as a2:
            assert {c.id for c in a2.runtime.concern_store.iter_all()} == ids1
            cite = a2.runtime.concern_store.get("c-cite")
            assert cite is not None
            before = cite.metrics.activations
            a2.handle("What is concern weaving?")
            cite2 = a2.runtime.concern_store.get("c-cite")
            assert cite2 is not None
            assert cite2.metrics.activations == before + 1

    def test_jsonl_round_trip_replay(self, tmp_path: Path, example_modules) -> None:
        agent_mod, _ = example_modules
        db = tmp_path / "state.db"
        log = tmp_path / "session.jsonl"

        with agent_mod.PersistentAgent(db, session_jsonl=log) as agent:
            agent.handle("Who invented the COAT runtime?")
            agent.handle("Tell me how concerns get matched.")

        result = replay_session_file(log)
        assert result.ok
        assert result.turns == 2

    def test_explicit_empty_concerns_skips_seed(self, tmp_path: Path, example_modules) -> None:
        agent_mod, _ = example_modules
        db = tmp_path / "empty.db"
        with agent_mod.PersistentAgent(db, session_jsonl=None, concerns=[]) as agent:
            assert list(agent.runtime.concern_store.iter_all()) == []
            report = agent.handle("Who invented the COAT runtime?")
            assert report.active_concern_ids == []

    def test_handle_without_context_manager_does_not_mutate_state(
        self, tmp_path: Path, example_modules
    ) -> None:
        """Codex P2 on PR-16: precondition must fire before ``on_joinpoint``.

        If the recorder is not open but ``session_jsonl`` was set, the agent
        must refuse the turn *before* mutating the DCN activation log or
        bumping lifecycle metrics; otherwise the on-disk state drifts from
        the never-written JSONL.
        """
        agent_mod, _ = example_modules
        db = tmp_path / "state.db"
        log = tmp_path / "session.jsonl"

        agent = agent_mod.PersistentAgent(db, session_jsonl=log)
        try:
            cite_before = agent.runtime.concern_store.get("c-cite")
            assert cite_before is not None
            log_before = list(agent.runtime.dcn_store.activation_log())

            with pytest.raises(RuntimeError, match="with PersistentAgent"):
                agent.handle("Who invented the COAT runtime?")

            cite_after = agent.runtime.concern_store.get("c-cite")
            assert cite_after is not None
            assert cite_after.metrics.activations == cite_before.metrics.activations
            assert list(agent.runtime.dcn_store.activation_log()) == log_before
            assert not log.exists()
        finally:
            agent.runtime.concern_store.close()
            agent.runtime.dcn_store.close()


class TestCli:
    def test_main_default_prompts(self, tmp_path: Path, example_modules, capsys) -> None:
        _, main_mod = example_modules
        db = tmp_path / "s.db"
        log = tmp_path / "s.jsonl"
        rc = main_mod.main(
            argv=[
                "--state-db",
                str(db),
                "--session-log",
                str(log),
            ]
        )
        out = capsys.readouterr().out
        assert rc == 0
        assert "Summary: 2 turn(s)" in out
        assert log.exists()
        assert replay_session_file(log).ok

    def test_main_replay_clean(self, tmp_path: Path, example_modules, capsys) -> None:
        agent_mod, main_mod = example_modules
        db = tmp_path / "s.db"
        log = tmp_path / "s.jsonl"
        with agent_mod.PersistentAgent(db, session_jsonl=log) as agent:
            agent.handle("What is concern weaving?")

        rc = main_mod.main(argv=["--replay", str(log)])
        assert rc == 0
        assert "0 mismatch" in capsys.readouterr().out
