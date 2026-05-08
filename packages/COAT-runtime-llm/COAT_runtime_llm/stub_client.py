"""Compatibility re-export of the canonical in-process stub.

The deterministic, dependency-free stub LLM client used by tests and
the M1 example lives in :mod:`COAT_runtime_core.llm` (it ships with the
core runtime so the in-proc happy path stays runnable without any
optional extras).

Earlier scaffolding put a placeholder in this module that raised
``NotImplementedError`` from every method. This left the documented
import path ``from COAT_runtime_llm import StubLLMClient`` pointing at
a broken class. We now re-export the working core stub here so:

* host code that imports from :mod:`COAT_runtime_llm` keeps working,
* there is exactly one ``StubLLMClient`` implementation in the
  monorepo,
* the ``COAT_runtime_llm`` package can stay focused on real provider
  adapters.
"""

from __future__ import annotations

from COAT_runtime_core.llm import StubLLMClient

__all__ = ["StubLLMClient"]
