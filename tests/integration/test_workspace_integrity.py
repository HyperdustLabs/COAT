"""Integration test: every workspace package can be imported together.

Catches situations where two packages declare colliding modules or
broken cross-package imports.
"""

from __future__ import annotations

import importlib

import pytest

WORKSPACE_PACKAGES = [
    "opencoat_runtime_protocol",
    "opencoat_runtime_core",
    "opencoat_runtime_storage",
    "opencoat_runtime_llm",
    "opencoat_runtime_host_sdk",
    "opencoat_runtime_daemon",
    "opencoat_runtime_cli",
    "opencoat_runtime_host_openclaw",
    "opencoat_runtime_host_hermes",
    "opencoat_runtime_host_langgraph",
    "opencoat_runtime_host_autogen",
    "opencoat_runtime_host_crewai",
    "opencoat_runtime_host_custom",
]


@pytest.mark.parametrize("modname", WORKSPACE_PACKAGES)
def test_workspace_package_imports(modname: str) -> None:
    importlib.import_module(modname)


def test_facade_only_depends_on_protocol_and_ports() -> None:
    """The facade construction must not require any storage / llm code."""
    from opencoat_runtime_core import OpenCOATRuntime, RuntimeConfig

    class _S:
        def upsert(self, c):
            return c

        def get(self, _):
            return None

        def delete(self, _):
            return None

        def list(self, **_):
            return []

        def search(self, *_, **__):
            return []

        def iter_all(self):
            return iter([])

    class _D:
        def add_node(self, _):
            return None

        def remove_node(self, _):
            return None

        def add_edge(self, *a, **k):
            return None

        def remove_edge(self, *a, **k):
            return None

        def neighbors(self, *a, **k):
            return []

        def log_activation(self, *a, **k):
            return None

        def activation_log(self, *a, **k):
            return iter([])

        def merge(self, *a, **k):
            return None

        def archive(self, *a, **k):
            return None

    class _L:
        def complete(self, *a, **k):
            return ""

        def chat(self, *a, **k):
            return ""

        def structured(self, *a, **k):
            return {}

        def score(self, *a, **k):
            return 0.0

    rt = OpenCOATRuntime(RuntimeConfig(), concern_store=_S(), dcn_store=_D(), llm=_L())
    assert rt.config.budgets.max_active_concerns == 12
