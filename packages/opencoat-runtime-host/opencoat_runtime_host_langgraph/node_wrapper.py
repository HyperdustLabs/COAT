"""Wrap a LangGraph node so its enter/exit emit joinpoints — M7."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def joinpoint_node(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(node: Callable[..., Any]) -> Callable[..., Any]:
        raise NotImplementedError

    return decorator
