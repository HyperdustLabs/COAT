"""GET/POST /v1/concerns — CRUD + search."""

from __future__ import annotations

from opencoat_runtime_protocol import Concern


class ConcernAPI:
    def list(self, **filters: str) -> list[Concern]:
        raise NotImplementedError

    def get(self, concern_id: str) -> Concern | None:
        raise NotImplementedError

    def create(self, concern: Concern) -> Concern:
        raise NotImplementedError
