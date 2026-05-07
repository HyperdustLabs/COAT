"""``/healthz`` and ``/readyz`` probes."""

from __future__ import annotations


class HealthCheck:
    def healthz(self) -> dict:
        raise NotImplementedError

    def readyz(self) -> dict:
        raise NotImplementedError
