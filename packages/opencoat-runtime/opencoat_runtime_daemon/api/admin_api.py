"""POST /v1/admin/* — heartbeat / reload / backup / restore."""

from __future__ import annotations


class AdminAPI:
    def heartbeat(self) -> dict:
        raise NotImplementedError

    def reload(self) -> dict:
        raise NotImplementedError
