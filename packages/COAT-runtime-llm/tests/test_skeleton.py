"""M0 smoke tests for LLM client skeletons."""

from __future__ import annotations

import importlib

import pytest


@pytest.mark.parametrize(
    "modname",
    [
        "COAT_runtime_llm",
        "COAT_runtime_llm.base",
        "COAT_runtime_llm.stub_client",
        "COAT_runtime_llm.openai_client",
        "COAT_runtime_llm.anthropic_client",
        "COAT_runtime_llm.azure_openai_client",
        "COAT_runtime_llm.ollama_client",
    ],
)
def test_module_imports(modname: str) -> None:
    importlib.import_module(modname)


def test_stub_client_satisfies_protocol() -> None:
    from COAT_runtime_core.ports import LLMClient
    from COAT_runtime_llm import StubLLMClient

    assert isinstance(StubLLMClient(), LLMClient)
