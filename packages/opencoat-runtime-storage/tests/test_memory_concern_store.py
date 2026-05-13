"""Behavioural tests for :class:`MemoryConcernStore`."""

from __future__ import annotations

import pytest
from opencoat_runtime_core.ports import ConcernStore
from opencoat_runtime_protocol import Concern, ConcernKind, LifecycleState
from opencoat_runtime_storage.memory import MemoryConcernStore


def _concern(
    cid: str,
    *,
    name: str | None = None,
    description: str = "",
    kind: ConcernKind = ConcernKind.CONCERN,
    tags: list[str] | None = None,
    lifecycle: LifecycleState = LifecycleState.CREATED,
) -> Concern:
    return Concern(
        id=cid,
        kind=kind,
        name=name or cid,
        description=description,
        generated_tags=tags or [],
        lifecycle_state=lifecycle,
    )


# ---------------------------------------------------------------------------
# Protocol shape
# ---------------------------------------------------------------------------


def test_implements_protocol() -> None:
    assert isinstance(MemoryConcernStore(), ConcernStore)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def test_upsert_returns_independent_copy() -> None:
    store = MemoryConcernStore()
    original = _concern("c1", name="alpha")

    returned = store.upsert(original)
    assert returned.id == "c1"
    assert returned is not original

    returned.name = "mutated-by-caller"
    assert store.get("c1") is not None
    assert store.get("c1").name == "alpha"


def test_get_returns_independent_copy() -> None:
    store = MemoryConcernStore()
    store.upsert(_concern("c1", name="alpha"))

    a = store.get("c1")
    b = store.get("c1")
    assert a == b
    assert a is not b
    a.name = "tampered"
    assert store.get("c1").name == "alpha"


def test_get_missing_returns_none() -> None:
    assert MemoryConcernStore().get("nope") is None


def test_upsert_overwrites_existing() -> None:
    store = MemoryConcernStore()
    store.upsert(_concern("c1", name="v1"))
    store.upsert(_concern("c1", name="v2"))

    assert store.get("c1").name == "v2"
    assert len(store) == 1


def test_upsert_rejects_empty_id() -> None:
    store = MemoryConcernStore()
    with pytest.raises(ValueError):
        store.upsert(_concern(""))


def test_delete_is_idempotent() -> None:
    store = MemoryConcernStore()
    store.upsert(_concern("c1"))
    store.delete("c1")
    store.delete("c1")
    assert store.get("c1") is None


# ---------------------------------------------------------------------------
# Listing & filters
# ---------------------------------------------------------------------------


def test_list_preserves_insertion_order() -> None:
    store = MemoryConcernStore()
    for i in range(5):
        store.upsert(_concern(f"c{i}", name=f"n{i}"))

    ids = [c.id for c in store.list()]
    assert ids == ["c0", "c1", "c2", "c3", "c4"]


def test_list_filters_combine_with_and() -> None:
    store = MemoryConcernStore()
    store.upsert(_concern("a", kind=ConcernKind.CONCERN, tags=["billing"]))
    store.upsert(_concern("b", kind=ConcernKind.CONCERN, tags=["billing", "fraud"]))
    store.upsert(
        _concern("m", kind=ConcernKind.META_CONCERN, tags=["billing"]),
    )

    billing = {c.id for c in store.list(tag="billing")}
    assert billing == {"a", "b", "m"}

    concerns_only = {c.id for c in store.list(kind="concern")}
    assert concerns_only == {"a", "b"}

    intersect = {c.id for c in store.list(kind="concern", tag="fraud")}
    assert intersect == {"b"}


def test_list_lifecycle_filter() -> None:
    store = MemoryConcernStore()
    store.upsert(_concern("a", lifecycle=LifecycleState.ACTIVE))
    store.upsert(_concern("b", lifecycle=LifecycleState.ARCHIVED))

    active = {c.id for c in store.list(lifecycle_state="active")}
    assert active == {"a"}


def test_list_limit_truncates_after_filter() -> None:
    store = MemoryConcernStore()
    for i in range(10):
        store.upsert(_concern(f"c{i}", tags=["x"]))

    out = store.list(tag="x", limit=3)
    assert [c.id for c in out] == ["c0", "c1", "c2"]


def test_list_negative_limit_returns_empty() -> None:
    store = MemoryConcernStore()
    store.upsert(_concern("a"))
    assert store.list(limit=-1) == []


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def test_search_matches_name_and_description_case_insensitive() -> None:
    store = MemoryConcernStore()
    store.upsert(_concern("a", name="Refund policy", description="when to issue refunds"))
    store.upsert(_concern("b", name="Greeting", description="how to greet customers"))
    store.upsert(_concern("c", name="Tax rules", description="VAT and refund interaction"))

    hits = {c.id for c in store.search("REFUND")}
    assert hits == {"a", "c"}


def test_search_empty_query_returns_empty() -> None:
    store = MemoryConcernStore()
    store.upsert(_concern("a", name="hi"))
    assert store.search("") == []
    assert store.search("   ") == []


def test_search_respects_limit() -> None:
    store = MemoryConcernStore()
    for i in range(5):
        store.upsert(_concern(f"c{i}", name=f"refund-{i}"))

    assert len(store.search("refund", limit=2)) == 2


# ---------------------------------------------------------------------------
# Iteration & helpers
# ---------------------------------------------------------------------------


def test_iter_all_yields_independent_copies() -> None:
    store = MemoryConcernStore()
    store.upsert(_concern("a", name="orig"))

    seen = list(store.iter_all())
    assert len(seen) == 1
    seen[0].name = "tampered"
    assert store.get("a").name == "orig"


def test_contains_and_len() -> None:
    store = MemoryConcernStore()
    assert "a" not in store
    store.upsert(_concern("a"))
    assert "a" in store
    assert 123 not in store  # type: ignore[operator]
    assert len(store) == 1
    store.clear()
    assert len(store) == 0
