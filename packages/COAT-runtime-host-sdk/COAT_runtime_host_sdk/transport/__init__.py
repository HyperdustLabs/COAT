"""Transport implementations for the host SDK.

Each module exposes a small class with ``connect`` / ``emit`` methods.
M0 is skeleton-only.
"""

from . import http, inproc, socket

__all__ = ["http", "inproc", "socket"]
