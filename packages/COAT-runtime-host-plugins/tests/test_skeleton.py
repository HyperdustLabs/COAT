"""M0 smoke tests — every host adapter imports and satisfies HostAdapter."""

from __future__ import annotations

import importlib

import pytest
from COAT_runtime_core.ports import HostAdapter

ADAPTERS = [
    ("COAT_runtime_host_openclaw", "OpenClawAdapter"),
    ("COAT_runtime_host_hermes", "HermesAdapter"),
    ("COAT_runtime_host_langgraph", "LangGraphAdapter"),
    ("COAT_runtime_host_autogen", "AutoGenAdapter"),
    ("COAT_runtime_host_crewai", "CrewAIAdapter"),
    ("COAT_runtime_host_custom", "CustomAdapter"),
]


@pytest.mark.parametrize("modname,clsname", ADAPTERS)
def test_adapter_module_imports(modname: str, clsname: str) -> None:
    mod = importlib.import_module(modname)
    cls = getattr(mod, clsname)
    inst = cls() if clsname != "CustomAdapter" else cls("custom")
    assert isinstance(inst, HostAdapter)
    assert isinstance(inst.host_name, str)


def test_event_maps_have_required_keys() -> None:
    from COAT_runtime_host_crewai import CREWAI_EVENT_MAP
    from COAT_runtime_host_hermes import HERMES_EVENT_MAP
    from COAT_runtime_host_langgraph import LANGGRAPH_EVENT_MAP
    from COAT_runtime_host_openclaw import OPENCLAW_EVENT_MAP

    for evmap in (OPENCLAW_EVENT_MAP, HERMES_EVENT_MAP, LANGGRAPH_EVENT_MAP, CREWAI_EVENT_MAP):
        assert isinstance(evmap, dict)
        assert all(isinstance(k, str) and isinstance(v, str) for k, v in evmap.items())
