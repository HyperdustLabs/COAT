"""The facade methods raise NotImplementedError until M1 — verify that contract."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from COAT_runtime_core import COATRuntime, RuntimeConfig
from COAT_runtime_core.runtime import RuntimeEvent


def _runtime() -> COATRuntime:
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

    return COATRuntime(RuntimeConfig(), concern_store=_S(), dcn_store=_D(), llm=_L())


def test_on_joinpoint_not_implemented_yet() -> None:
    rt = _runtime()
    from COAT_runtime_protocol import JoinpointEvent

    jp = JoinpointEvent(
        id="jp-1", level=1, name="before_response", host="test", ts=datetime.now(UTC)
    )
    with pytest.raises(NotImplementedError):
        rt.on_joinpoint(jp)


def test_on_event_not_implemented_yet() -> None:
    rt = _runtime()
    with pytest.raises(NotImplementedError):
        rt.on_event(RuntimeEvent(type="test", ts=datetime.now(UTC), payload={}))


def test_tick_not_implemented_yet() -> None:
    rt = _runtime()
    with pytest.raises(NotImplementedError):
        rt.tick(datetime.now(UTC))
