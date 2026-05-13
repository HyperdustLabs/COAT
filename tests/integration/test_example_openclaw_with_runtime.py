"""Integration smoke for ``examples/04_openclaw_with_runtime`` (M5 #32).

Loaded via ``importlib`` because the package directory name starts with
a digit (same pattern as ``test_example_long_running_daemon``).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

EXAMPLE_DIR = Path(__file__).resolve().parents[2] / "examples" / "04_openclaw_with_runtime"
PKG_NAME = "_opencoat_example_openclaw_with_runtime"


def _load_example_main():
    """Return the loaded ``main`` module."""
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
    return sys.modules[f"{PKG_NAME}.main"]


@pytest.fixture(scope="module")
def main_mod():
    return _load_example_main()


class TestOpenClawExampleProgrammatic:
    def test_run_demo_uninstalls_all_callbacks(self, main_mod) -> None:
        report = main_mod.run_demo(session_id="pytest-openclaw")
        assert report.subscription_count_after_uninstall == 0

    def test_memory_bridge_mirrors_demo_key(self, main_mod) -> None:
        report = main_mod.run_demo(session_id="pytest-openclaw-mem")
        assert report.memory_bridge_logged_demo_key is True
        assert report.memory_activation_count >= 1

    def test_last_injection_includes_memory_row(self, main_mod) -> None:
        report = main_mod.run_demo(session_id="pytest-openclaw-inj")
        assert report.last_injection is not None
        assert any(
            row.target == "memory_write.policy_note" for row in report.last_injection.injections
        )


class TestOpenClawExampleCli:
    def test_main_quiet_exits_zero(self, main_mod) -> None:
        assert main_mod.main(["--quiet"]) == 0
