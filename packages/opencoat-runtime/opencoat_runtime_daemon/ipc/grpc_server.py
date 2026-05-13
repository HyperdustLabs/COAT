"""Optional gRPC server — post-M5 milestone."""

from __future__ import annotations


class GrpcServer:
    def serve(self) -> None:
        raise NotImplementedError
