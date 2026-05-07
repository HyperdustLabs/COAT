"""Top-level :class:`Client` — chooses a transport based on the connect URI."""

from __future__ import annotations

from typing import Any

from COAT_runtime_protocol import ConcernInjection, JoinpointEvent


class Client:
    """Entrypoint for host code.

    Connect string formats:

    * ``inproc://`` — direct in-process call (M1)
    * ``unix:///run/COATr.sock`` — Unix domain socket (M4)
    * ``http://127.0.0.1:7878`` — HTTP / JSON-RPC (M4)
    """

    def __init__(self, transport: Any) -> None:
        self._transport = transport

    @classmethod
    def connect(cls, uri: str) -> Client:
        raise NotImplementedError

    def emit(self, joinpoint: JoinpointEvent) -> ConcernInjection | None:
        raise NotImplementedError
