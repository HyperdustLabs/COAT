"""Skeleton template for user-defined host adapters.

Copy this directory, rename the package, and implement the four protocol
methods on :class:`CustomAdapter`. The runtime will discover your adapter
through the ``plugins.hosts`` config entry or directly via wiring.
"""

from .adapter import CustomAdapter

__all__ = ["CustomAdapter"]
