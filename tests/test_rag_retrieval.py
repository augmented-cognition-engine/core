from __future__ import annotations

from contextlib import asynccontextmanager

import pytest

from core.engine.core.exceptions import ValidationError
from core.engine.search.intelligence import reciprocal_rank_fusion, search_intelligence


class _Embedder:
    def __init__(self, *, dimensions: int = 768, fail: bool = False) -> None:
        self.dimensions = dimensions
        self.fail = fail

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if self.fail:
            raise RuntimeError("embedding unavailable")
        return [[0.01] * self.dimensions for _ in texts]


class _DB:
    def __init__(self, *, vector_failure: bool = False) -> None:
        self.queries: list[tuple[str, dict]] = []
        self.vector_failure = vector_failure

    async def query(self, statement: str, params: dict | None = None):
        self.queries.append((statement, params or {}))
        if "search::score(0)" in statement:
            return [
                {
                    "id": "insight:lexical",
                    "content": "retry webhooks with exponential backoff",
                    "confidence": 0.7,
                    "lexical_score": 3.2,
                }
            ]
        if "vector::distance::knn()" in statement:
            if self.vector_failure:
                raise RuntimeError("vector index unavailable")
            return [
                {
                    "id": "insight:vector",
                    "content": "delivery retries use increasing delays",
                    "confidence": 0.8,
                    "vector_distance": 0.12,
                },
                {
                    "id": "insight:lexical",
                    "content": "retry webhooks with exponential backoff",
                    "confidence": 0.7,
                    "vector_distance": 0.18,
                },
            ]
        return []


class _Pool:
    def __init__(self, db: _DB) -> None:
        self.db = db

    @asynccontextmanager
    async def connection(self):
        yield self.db


def test_rrf_rewards_candidates_found_by_both_signals() -> None:
    lexical = [{"id": "insight:both"}, {"id": "insight:lexical"}]
    vector = [{"id": "insight:vector"}, {"id": "insight:both"}]

    result = reciprocal_rank_fusion(lexical, vector, limit=3)

    assert [row["id"] for row in result] == ["insight:both", "insight:vector", "insight:lexical"]


def test_rrf_serializes_database_record_ids_for_http_responses() -> None:
    class _RecordID:
        def __str__(self) -> str:
            return "insight:database_id"

    result = reciprocal_rank_fusion([{"id": _RecordID(), "content": "serializable"}], [], limit=1)

    assert result[0]["id"] == "insight:database_id"


@pytest.mark.asyncio
async def test_search_uses_bm25_score_and_indexed_knn() -> None:
    db = _DB()
    result = await search_intelligence(
        "webhook retry policy",
        "product:test",
        db_pool=_Pool(db),
        embedder=_Embedder(),
    )

    statements = "\n".join(statement for statement, _params in db.queries)
    assert "content @0@ $query" in statements
    assert "search::score(0) AS lexical_score" in statements
    assert "ORDER BY lexical_score DESC" in statements
    assert "embedding <|" in statements
    assert "vector::distance::knn() AS vector_distance" in statements
    assert result["results"][0]["id"] == "insight:lexical"
    assert result["retrieval"]["state"] == "complete"
    assert result["retrieval"]["signals"]["vector"]["state"] == "complete"


@pytest.mark.asyncio
async def test_dimension_mismatch_is_visible_and_skips_vector_query() -> None:
    db = _DB()
    result = await search_intelligence(
        "webhook retry policy",
        "product:test",
        db_pool=_Pool(db),
        embedder=_Embedder(dimensions=1_024),
    )

    statements = "\n".join(statement for statement, _params in db.queries)
    assert "vector::distance::knn()" not in statements
    assert result["count"] == 1
    assert result["retrieval"]["state"] == "degraded"
    assert "embedding_dimension_mismatch" in result["retrieval"]["degraded_reasons"]


@pytest.mark.asyncio
async def test_vector_failure_fails_open_with_a_degraded_receipt() -> None:
    result = await search_intelligence(
        "webhook retry policy",
        "product:test",
        db_pool=_Pool(_DB(vector_failure=True)),
        embedder=_Embedder(),
    )

    assert result["count"] == 1
    assert result["retrieval"]["state"] == "degraded"
    assert result["retrieval"]["signals"]["vector"]["reason"] == "vector_retrieval_failed:RuntimeError"


@pytest.mark.asyncio
async def test_distant_vector_candidates_are_not_returned_for_no_answer_query() -> None:
    db = _DB()

    async def distant_query(statement: str, params: dict | None = None):
        db.queries.append((statement, params or {}))
        if "vector::distance::knn()" in statement:
            return [
                {
                    "id": "insight:irrelevant",
                    "content": "unrelated nearest neighbor",
                    "vector_distance": 0.99,
                }
            ]
        return []

    db.query = distant_query
    result = await search_intelligence(
        "no matching subject",
        "product:test",
        db_pool=_Pool(db),
        embedder=_Embedder(),
    )

    assert result["results"] == []
    assert result["retrieval"]["signals"]["vector"]["maximum_distance"] == 0.45


@pytest.mark.asyncio
async def test_widened_vector_cutoff_recalls_candidate_and_receipt_matches(monkeypatch) -> None:
    db = _DB()

    async def distant_query(statement: str, params: dict | None = None):
        db.queries.append((statement, params or {}))
        if "vector::distance::knn()" in statement:
            return [
                {
                    "id": "insight:widened",
                    "content": "relevant prose outside the compatibility cutoff",
                    "vector_distance": 0.65,
                }
            ]
        return []

    db.query = distant_query
    monkeypatch.setattr("core.engine.search.intelligence.settings.rag_vector_max_distance", 0.7)

    result = await search_intelligence(
        "prose corpus concept",
        "product:widened",
        db_pool=_Pool(db),
        embedder=_Embedder(),
    )

    assert [row["id"] for row in result["results"]] == ["insight:widened"]
    assert result["retrieval"]["signals"]["vector"]["maximum_distance"] == 0.7
    assert result["retrieval"]["signals"]["vector"]["distance_omitted"] == 0


@pytest.mark.asyncio
async def test_vector_queries_remain_product_scoped_when_cutoff_is_widened(monkeypatch) -> None:
    db = _DB()
    monkeypatch.setattr("core.engine.search.intelligence.settings.rag_vector_max_distance", 2.0)

    result = await search_intelligence(
        "webhook retry policy",
        "product:isolated",
        db_pool=_Pool(db),
        embedder=_Embedder(),
    )

    retrieval_queries = [
        (statement, params)
        for statement, params in db.queries
        if "FROM insight" in statement and ("search::score(0)" in statement or "vector::distance::knn()" in statement)
    ]
    assert len(retrieval_queries) == 2
    for statement, params in retrieval_queries:
        assert "product = <record>$product" in statement
        assert params["product"] == "product:isolated"
    assert result["retrieval"]["product_id"] == "product:isolated"
    assert result["retrieval"]["signals"]["vector"]["maximum_distance"] == 2.0


@pytest.mark.asyncio
async def test_invalid_search_inputs_fail_before_database_access() -> None:
    db = _DB()
    with pytest.raises(ValidationError, match="query must be non-empty"):
        await search_intelligence(" ", "product:test", db_pool=_Pool(db), embedder=_Embedder())
    assert db.queries == []
