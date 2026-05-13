"""Apply a :class:`~opencoat_runtime_protocol.ConcernInjection` into OpenClaw host context (M5 #29).

OpenClaw carries mutable prompt / response state as nested ``dict`` trees
(``runtime_prompt.*``, ``response.*``, …). The weaver already chose a
**target** string (``runtime_prompt.output_format``) and a
:class:`~opencoat_runtime_protocol.WeavingOperation`; this module is the
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

Wildcard targets
----------------

Default weaving targets are allowed to use ``*`` segments — e.g.
``tool_call.arguments.*`` or ``memory_write.*`` — to mean "apply this
advice to every existing field under the parent" (Codex P1 on PR #29).
The injector resolves ``*`` against the **current** host context:

* Trailing ``*`` — iterate every key in the parent dict and apply the
  operation to each one. If the parent is empty or not a dict, the
  injection is dropped rather than written to a literal ``"*"`` key,
  because there is no concrete target for the advice yet.
* Mid-path ``*`` — recurse into every dict-valued child at that
  level and continue walking with the remaining segments.
"""

from __future__ import annotations

import copy
from typing import Any

from opencoat_runtime_protocol import ConcernInjection, Injection, WeavingOperation

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


_WILDCARD = "*"


def _split_target(target: str) -> list[str]:
    return [p for p in target.split(".") if p]


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

    # ------------------------------------------------------------------
    # one Injection row
    # ------------------------------------------------------------------

    def _apply_one(self, out: dict[str, Any], row: Injection) -> None:
        if not self._config.inject_into_runtime_prompt and row.target.startswith("runtime_prompt."):
            return
        segments = _split_target(row.target)
        if not segments:
            return
        self._apply_segments(out, segments, row)

    def _apply_segments(
        self,
        node: Any,
        segments: list[str],
        row: Injection,
    ) -> None:
        """Walk ``segments`` against ``node``, expanding ``*`` segments.

        ``node`` is always the *current* parent dict — never the leaf,
        because we still need to dispatch to the mode-specific writer
        once we hit the final segment.
        """
        if not isinstance(node, dict):
            # Walked off a string/list leaf — nothing sensible to write.
            return

        head, *rest = segments
        if head == _WILDCARD:
            # Mid-path wildcard → recurse into every dict-valued child.
            # Trailing wildcard with no remaining segments → apply to
            # every existing key in ``node``; drop on empty parent so we
            # never create a literal ``"*"`` key (Codex P1 on PR #29).
            if rest:
                for child in node.values():
                    if isinstance(child, dict):
                        self._apply_segments(child, rest, row)
                return
            for key in list(node.keys()):
                self._write_leaf(node, key, row)
            return

        if not rest:
            self._write_leaf(node, head, row)
            return

        nxt = node.get(head)
        if not isinstance(nxt, dict):
            nxt = {}
            node[head] = nxt
        self._apply_segments(nxt, rest, row)

    # ------------------------------------------------------------------
    # writers
    # ------------------------------------------------------------------

    def _write_leaf(self, parent: dict[str, Any], leaf: str, row: Injection) -> None:
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
