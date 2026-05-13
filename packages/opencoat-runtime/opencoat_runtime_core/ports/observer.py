"""Observability port — single sink for metric / span / log events.

Concrete observers can forward to OpenTelemetry, structured logs, or a
test sink.  The default is a no-op.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Observer(Protocol):
    def on_metric(self, name: str, value: float, **labels: str) -> None: ...
    def on_span(self, name: str, **attrs: Any) -> _SpanCtx: ...
    def on_log(self, level: str, message: str, **fields: Any) -> None: ...


class _SpanCtx(Protocol):
    """Context-manager handle for a tracing span."""

    def __enter__(self) -> _SpanCtx: ...
    def __exit__(self, exc_type, exc, tb) -> None: ...
    def set_attribute(self, key: str, value: Any) -> None: ...


class NullObserver:
    """Default no-op observer used when nothing is wired."""

    def on_metric(self, name: str, value: float, **labels: str) -> None:
        return None

    def on_span(self, name: str, **attrs: Any) -> _NullSpan:
        return _NullSpan()

    def on_log(self, level: str, message: str, **fields: Any) -> None:
        return None


class _NullSpan:
    def __enter__(self) -> _NullSpan:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def set_attribute(self, key: str, value: Any) -> None:
        return None
