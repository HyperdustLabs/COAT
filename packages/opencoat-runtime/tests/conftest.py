"""Pytest defaults for the ``opencoat-runtime`` package test suite."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _force_memory_stores_for_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid touching ``~/.opencoat/*.sqlite`` during parallel ``pytest``.

    The bundled :file:`default.yaml` now defaults to sqlite-backed
    persistence (production parity). Tests that build a runtime via
    :func:`load_config` overlay back to in-memory stores unless they
    explicitly ``delenv`` ``OPENCOAT_TEST_MEMORY_STORES`` first.
    """
    monkeypatch.setenv("OPENCOAT_TEST_MEMORY_STORES", "1")
