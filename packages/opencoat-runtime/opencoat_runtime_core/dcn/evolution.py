"""DCN evolver — long-term graph maintenance run on heartbeat."""

from __future__ import annotations


class DCNEvolver:
    def decay(self) -> int:
        raise NotImplementedError

    def merge(self) -> int:
        raise NotImplementedError

    def archive(self) -> int:
        raise NotImplementedError

    def optimize(self) -> int:
        raise NotImplementedError
