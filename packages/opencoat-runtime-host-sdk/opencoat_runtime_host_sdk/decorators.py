"""Decorators that wrap host functions with implicit joinpoint emission."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any

from .client import Client


def joinpoint(name: str, *, client: Client, level: int = 1) -> Callable[..., Any]:
    """Wrap a function so that calling it emits ``name`` before/after.

    M1 fills in ``before_*`` / ``after_*`` semantics. M0 keeps the decorator
    as a no-op pass-through so host code can be written today.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return func(*args, **kwargs)

        wrapper.__opencoat_joinpoint__ = {  # type: ignore[attr-defined]
            "name": name,
            "level": level,
        }
        return wrapper

    return decorator
