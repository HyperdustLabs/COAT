"""Render a shallow DCN snapshot to Graphviz DOT (M4 PR-22).

A *full* Deep Concern Network export is gated on a future
``dcn.snapshot`` RPC that exposes nodes + edges over a clean port API
(the M1 ``DCNStore`` Protocol doesn't yet enumerate either). Until that
lands, ``COATr dcn export`` ships what the existing RPC methods can
return — the concern list plus the activation history — and this
module turns that into a readable DOT graph:

* every concern becomes a box node, labelled with its name and
  lifecycle state;
* every distinct joinpoint that appears in the activation log becomes
  an oval node;
* one edge per ``(joinpoint → concern)`` activation, weighted by the
  number of times the pair appears in the log.

The resulting graph is bipartite-ish and conveys *which concerns are
firing on which joinpoints*, which is the most useful thing to draw
before we have real DCN edges.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


def _quote(label: str) -> str:
    """DOT-quote a label, escaping embedded quotes/newlines."""
    text = str(label).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{text}"'


def _node_id(prefix: str, raw: str) -> str:
    """Build a uniquely identifying DOT node id from ``raw``.

    DOT accepts double-quoted strings as IDs (cf. the grammar in
    https://graphviz.org/doc/info/lang.html), so we keep the raw
    string verbatim — only escaping characters that would break the
    quote — and prefix it with ``"c:"`` / ``"j:"`` to keep the
    concern and joinpoint namespaces disjoint.

    Previously we ran ``re.sub(r"[^A-Za-z0-9_]", "_", raw)``, which
    silently collapsed e.g. ``a-b`` and ``a_b`` onto the same node id
    — Graphviz then merged the two nodes and the rendered graph
    misrepresented the underlying concerns/edges (Codex P2 on PR-22,
    #26). Quoting sidesteps the collision entirely.
    """
    return _quote(f"{prefix}:{raw}")


def dcn_to_dot(snapshot: Mapping[str, Any]) -> str:
    """Render ``snapshot`` to DOT.

    ``snapshot`` shape (matches ``COATr dcn export --format json``):

    .. code-block:: json

        {
          "concerns": [{"id": "...", "name": "...", "lifecycle_state": "..."}],
          "activation_log": [{"concern_id": "...", "joinpoint_id": "...",
                              "score": 0.8, "ts": "..."}]
        }

    Returns a single string ready to feed into ``dot -Tsvg``.
    """
    concerns: Iterable[Mapping[str, Any]] = snapshot.get("concerns") or []
    activations: Iterable[Mapping[str, Any]] = snapshot.get("activation_log") or []

    lines: list[str] = [
        "digraph DCN {",
        "  rankdir=LR;",
        '  graph [fontname="Helvetica"];',
        '  node  [fontname="Helvetica"];',
        '  edge  [fontname="Helvetica", fontsize=10];',
    ]

    concern_index: dict[str, str] = {}
    for c in concerns:
        cid = str(c.get("id") or "")
        if not cid:
            continue
        node_id = _node_id("c", cid)
        concern_index[cid] = node_id
        name = c.get("name") or cid
        state = c.get("lifecycle_state") or "?"
        label = f"{name}\n({state})"
        lines.append(f"  {node_id} [shape=box, label={_quote(label)}];")

    joinpoint_index: dict[str, str] = {}
    edge_counts: dict[tuple[str, str], int] = {}
    for row in activations:
        cid = str(row.get("concern_id") or "")
        jp = str(row.get("joinpoint_id") or "")
        if not cid or not jp:
            continue
        if cid not in concern_index:
            # Activation references a concern we didn't get in the
            # snapshot — fabricate a stub so the edge is still drawn.
            stub = _node_id("c", cid)
            concern_index[cid] = stub
            lines.append(f"  {stub} [shape=box, style=dashed, label={_quote(cid)}];")
        if jp not in joinpoint_index:
            jp_id = _node_id("j", jp)
            joinpoint_index[jp] = jp_id
            lines.append(f"  {jp_id} [shape=oval, label={_quote(jp)}];")
        edge_counts[(jp, cid)] = edge_counts.get((jp, cid), 0) + 1

    for (jp, cid), count in sorted(edge_counts.items()):
        attrs = f"label={_quote(str(count))}" if count > 1 else ""
        suffix = f" [{attrs}]" if attrs else ""
        lines.append(f"  {joinpoint_index[jp]} -> {concern_index[cid]}{suffix};")

    lines.append("}")
    return "\n".join(lines) + "\n"


__all__ = ["dcn_to_dot"]
