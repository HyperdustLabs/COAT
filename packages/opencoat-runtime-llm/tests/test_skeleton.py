"""M0 smoke tests for LLM client skeletons."""

from __future__ import annotations

import importlib

import pytest


@pytest.mark.parametrize(
    "modname",
    [
        "opencoat_runtime_llm",
        "opencoat_runtime_llm.base",
        "opencoat_runtime_llm.stub_client",
        "opencoat_runtime_llm.openai_client",
        "opencoat_runtime_llm.anthropic_client",
        "opencoat_runtime_llm.azure_openai_client",
        "opencoat_runtime_llm.ollama_client",
    ],
)
def test_module_imports(modname: str) -> None:
    importlib.import_module(modname)


def test_stub_client_satisfies_protocol() -> None:
    from opencoat_runtime_core.ports import LLMClient
    from opencoat_runtime_llm import StubLLMClient

    assert isinstance(StubLLMClient(), LLMClient)
