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
