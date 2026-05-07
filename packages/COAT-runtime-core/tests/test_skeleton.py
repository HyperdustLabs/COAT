"""Smoke tests for the M0 core skeleton.

Goal: every module imports cleanly and exposes its declared public surface.
The actual behaviour is covered by tests added in M1 onwards.
"""

from __future__ import annotations

import importlib
import pkgutil

import pytest


@pytest.mark.parametrize(
    "modname",
    [
        "COAT_runtime_core",
        "COAT_runtime_core.config",
        "COAT_runtime_core.errors",
        "COAT_runtime_core.runtime",
        "COAT_runtime_core.types",
        "COAT_runtime_core.concern",
        "COAT_runtime_core.joinpoint",
        "COAT_runtime_core.pointcut",
        "COAT_runtime_core.pointcut.strategies",
        "COAT_runtime_core.advice",
        "COAT_runtime_core.weaving",
        "COAT_runtime_core.copr",
        "COAT_runtime_core.coordinator",
        "COAT_runtime_core.resolver",
        "COAT_runtime_core.dcn",
        "COAT_runtime_core.meta",
        "COAT_runtime_core.loops",
        "COAT_runtime_core.ports",
        "COAT_runtime_core.observability",
    ],
)
def test_module_imports(modname: str) -> None:
    importlib.import_module(modname)


def test_facade_constructible_with_dummy_ports() -> None:
    """The facade should construct from any objects that satisfy the protocols."""
    from COAT_runtime_core import COATRuntime, RuntimeConfig
    from COAT_runtime_core.ports.observer import NullObserver

    class _DummyConcernStore:
        def upsert(self, concern):
            return concern

        def get(self, concern_id):
            return None

        def delete(self, concern_id):
            return None

        def list(self, **_):
            return []

        def search(self, query, *, limit=20):
            return []

        def iter_all(self):
            return iter([])

    class _DummyDCNStore:
        def add_node(self, concern):
            return None

        def remove_node(self, concern_id):
            return None

        def add_edge(self, src, dst, relation_type, *, weight=1.0):
            return None

        def remove_edge(self, src, dst, relation_type):
            return None

        def neighbors(self, concern_id, *, relation_type=None):
            return []

        def log_activation(self, concern_id, joinpoint_id, score, ts):
            return None

        def activation_log(self, concern_id=None, *, limit=None):
            return iter([])

        def merge(self, src, dst):
            return None

        def archive(self, concern_id):
            return None

    class _DummyLLM:
        def complete(self, prompt, **_):
            return ""

        def chat(self, messages, **_):
            return ""

        def structured(self, messages, *, schema, **_):
            return {}

        def score(self, prompt, candidate, **_):
            return 0.0

    rt = COATRuntime(
        RuntimeConfig(),
        concern_store=_DummyConcernStore(),
        dcn_store=_DummyDCNStore(),
        llm=_DummyLLM(),
        observer=NullObserver(),
    )
    assert rt.config.schema_version == "0.2"


def test_no_stray_modules() -> None:
    """Walk the package tree and import every submodule to surface SyntaxErrors."""
    import COAT_runtime_core

    seen: list[str] = []
    for mod in pkgutil.walk_packages(
        COAT_runtime_core.__path__, prefix=COAT_runtime_core.__name__ + "."
    ):
        importlib.import_module(mod.name)
        seen.append(mod.name)
    assert seen, "expected to discover at least one submodule"
