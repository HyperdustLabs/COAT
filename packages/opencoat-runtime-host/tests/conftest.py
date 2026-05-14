"""Pytest defaults for ``opencoat-runtime-host`` tests."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _force_memory_stores_for_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    """Match ``opencoat-runtime`` tests — avoid touching real ``~/.opencoat`` sqlite."""
    monkeypatch.setenv("OPENCOAT_TEST_MEMORY_STORES", "1")
