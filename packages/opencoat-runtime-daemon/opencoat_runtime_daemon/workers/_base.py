"""Common worker base class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime


class Worker(ABC):
    """Synchronous worker invoked by the scheduler.

    Workers are stateless — all state lives in the stores.  Multiple instances
    can coexist behind a queue without coordination.
    """

    @abstractmethod
    def run(self, now: datetime) -> dict: ...
