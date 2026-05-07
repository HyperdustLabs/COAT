"""GET /v1/dcn/snapshot — DCN graph snapshot."""

from __future__ import annotations


class DCNAPI:
    def snapshot(self) -> dict:
        raise NotImplementedError
