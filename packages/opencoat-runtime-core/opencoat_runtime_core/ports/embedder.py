"""Embedding port — used by semantic pointcuts and the vector index."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable


@runtime_checkable
class Embedder(Protocol):
    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...
    @property
    def dimension(self) -> int: ...
