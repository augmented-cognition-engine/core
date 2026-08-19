import pytest


@pytest.fixture
def store():
    from core.engine.search.vector_store import VectorStore

    return VectorStore(dimensions=4)  # tiny dims for fast tests


@pytest.mark.asyncio
async def test_upsert_and_search(store):
    await store.upsert("file::foo", [1.0, 0.0, 0.0, 0.0], {"path": "foo.py"})
    await store.upsert("file::bar", [0.0, 1.0, 0.0, 0.0], {"path": "bar.py"})
    results = await store.search([1.0, 0.0, 0.0, 0.0], limit=2)
    assert len(results) >= 1
    assert results[0]["id"] == "file::foo"


@pytest.mark.asyncio
async def test_search_returns_score(store):
    await store.upsert("sym::a", [1.0, 0.0, 0.0, 0.0], {})
    results = await store.search([1.0, 0.0, 0.0, 0.0], limit=1)
    assert "score" in results[0]
    assert results[0]["score"] > 0.9


@pytest.mark.asyncio
async def test_search_empty_store(store):
    results = await store.search([1.0, 0.0, 0.0, 0.0], limit=5)
    assert results == []


@pytest.mark.asyncio
async def test_upsert_overwrites(store):
    await store.upsert("sym::x", [1.0, 0.0, 0.0, 0.0], {"version": 1})
    await store.upsert("sym::x", [0.5, 0.5, 0.0, 0.0], {"version": 2})
    results = await store.search([0.5, 0.5, 0.0, 0.0], limit=1)
    assert results[0]["version"] == 2


# --- payload-filter count/delete (PI9 ownership depth) ----------------------
# Point ids are per-process salted hashes and unrecoverable by a later process,
# so scoped deletion must select by payload — the same fields the embed hook
# writes (graph_id on file points, file on function points).


@pytest.mark.asyncio
async def test_count_and_delete_by_payload_scoped_to_matching_values(store):
    await store.upsert("a.py", [1.0, 0.0, 0.0, 0.0], {"path": "a.py", "graph_id": "g1"})
    await store.upsert("b.py", [0.0, 1.0, 0.0, 0.0], {"path": "b.py", "graph_id": "g1"})
    await store.upsert("c.py", [0.0, 0.0, 1.0, 0.0], {"path": "c.py", "graph_id": "g2"})
    await store.upsert("a.py::fn", [0.0, 0.0, 0.0, 1.0], {"file": "a.py", "name": "fn", "kind": "function"})

    assert await store.count_by_payload("graph_id", ["g1"]) == 2
    assert await store.count_by_payload("file", ["a.py"]) == 1

    removed = await store.delete_by_payload("graph_id", ["g1"])
    assert removed == 2
    assert await store.count_by_payload("graph_id", ["g1"]) == 0
    # the other graph's point and the function point are untouched
    assert await store.count_by_payload("graph_id", ["g2"]) == 1
    assert await store.count_by_payload("file", ["a.py"]) == 1

    removed_functions = await store.delete_by_payload("file", ["a.py"])
    assert removed_functions == 1
    assert await store.count_by_payload("file", ["a.py"]) == 0


@pytest.mark.asyncio
async def test_delete_by_payload_is_idempotent_and_validates_selector(store):
    await store.upsert("a.py", [1.0, 0.0, 0.0, 0.0], {"path": "a.py", "graph_id": "g1"})
    assert await store.delete_by_payload("graph_id", ["g1"]) == 1
    assert await store.delete_by_payload("graph_id", ["g1"]) == 0
    with pytest.raises(ValueError):
        await store.delete_by_payload("", ["g1"])
    with pytest.raises(ValueError):
        await store.count_by_payload("graph_id", [])
    with pytest.raises(ValueError):
        await store.count_by_payload("graph_id", ["  "])
