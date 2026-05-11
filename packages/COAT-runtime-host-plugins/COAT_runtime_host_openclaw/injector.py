"""Apply a :class:`~COAT_runtime_protocol.ConcernInjection` into OpenClaw host context (M5 #29).

OpenClaw carries mutable prompt / response state as nested ``dict`` trees
(``runtime_prompt.*``, ``response.*``, …). The weaver already chose a
**target** string (``runtime_prompt.output_format``) and a
:class:`~COAT_runtime_protocol.WeavingOperation`; this module is the
mechanical half that walks the tree and merges **content** strings.

Semantics (best-effort, host-agnostic):

* **INSERT / ANNOTATE / WARN / VERIFY / DEFER** — treat as *append* on
  string leaves (newline-separated). Unknown / non-string leaves are
  replaced with the incoming ``content`` so we never silently drop advice.
* **REPLACE / REWRITE / COMPRESS** — overwrite the leaf with ``content``.
* **SUPPRESS / BLOCK / ESCALATE** — overwrite with ``content`` (the
  weaver is expected to have turned policy into human-readable text).

When :attr:`OpenClawAdapterConfig.inject_into_runtime_prompt` is
``False``, injections whose ``target`` starts with ``"runtime_prompt."``
are skipped so hosts can lock down prompt mutation while still allowing
``response.*`` edits.
"""

from __future__ import annotations

import copy
from typing import Any

from COAT_runtime_protocol import ConcernInjection, Injection, WeavingOperation

from .config import OpenClawAdapterConfig

_APPEND_MODES: frozenset[WeavingOperation | str] = frozenset(
    {
        WeavingOperation.INSERT,
        WeavingOperation.ANNOTATE,
        WeavingOperation.WARN,
        WeavingOperation.VERIFY,
        WeavingOperation.DEFER,
        # wire may carry plain strings when round-tripped through JSON
        "insert",
        "annotate",
        "warn",
        "verify",
        "defer",
    }
)

_OVERWRITE_MODES: frozenset[WeavingOperation | str] = frozenset(
    {
        WeavingOperation.REPLACE,
        WeavingOperation.REWRITE,
        WeavingOperation.COMPRESS,
        "replace",
        "rewrite",
        "compress",
    }
)

_BLOCK_MODES: frozenset[WeavingOperation | str] = frozenset(
    {
        WeavingOperation.SUPPRESS,
        WeavingOperation.BLOCK,
        WeavingOperation.ESCALATE,
        "suppress",
        "block",
        "escalate",
    }
)


def _split_target(target: str) -> list[str]:
    return [p for p in target.split(".") if p]


def _parent_and_leaf(root: dict[str, Any], segments: list[str]) -> tuple[dict[str, Any], str]:
    """Walk ``segments[:-1]`` under ``root``, creating empty ``dict`` nodes."""
    cur: dict[str, Any] = root
    for key in segments[:-1]:
        nxt = cur.get(key)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[key] = nxt
        cur = nxt
    return cur, segments[-1]


class OpenClawInjector:
    """Merge :class:`ConcernInjection` rows into a host context dict."""

    def __init__(self, config: OpenClawAdapterConfig | None = None) -> None:
        self._config = config or OpenClawAdapterConfig()

    def apply(self, injection: ConcernInjection, host_context: dict[str, Any]) -> dict[str, Any]:
        """Return a **new** context with ``injection`` applied.

        Deep-copies ``host_context`` first so callers can diff before/after
        without accidental mutation of shared references.
        """
        out: dict[str, Any] = copy.deepcopy(host_context) if host_context else {}
        for row in injection.injections:
            self._apply_one(out, row)
        return out

    def _apply_one(self, out: dict[str, Any], row: Injection) -> None:
        if not self._config.inject_into_runtime_prompt and row.target.startswith("runtime_prompt."):
            return
        segments = _split_target(row.target)
        if not segments:
            return
        parent, leaf = _parent_and_leaf(out, segments)
        mode = row.mode
        if mode in _APPEND_MODES:
            self._append_at(parent, leaf, row.content)
        elif mode in _OVERWRITE_MODES or mode in _BLOCK_MODES:
            parent[leaf] = row.content
        else:
            # Unknown / future operation — safest default is append-like merge.
            self._append_at(parent, leaf, row.content)

    @staticmethod
    def _append_at(parent: dict[str, Any], leaf: str, content: str) -> None:
        cur = parent.get(leaf)
        if isinstance(cur, str) and cur:
            parent[leaf] = f"{cur}\n{content}"
        elif cur is None or cur == "":
            parent[leaf] = content
        else:
            # Non-string leaf (bool / list / nested dict) — replace rather than
            # stringify, so we don't corrupt host-typed slots.
            parent[leaf] = content


__all__ = ["OpenClawInjector"]
