"""Unit tests for the contributions aggregator. Exercises each metric
in isolation against a stubbed pool, plus the headline template + the
sub-query failure isolation contract."""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest


class _StubDB:
    """Stub that returns canned query results indexed by query substring."""

    def __init__(self, responses: dict[str, list[dict]]):
        self._responses = responses

    async def query(self, sql: str, params: dict | None = None):
        # Match by the table name appearing in the SQL string
        for needle, response in self._responses.items():
            if needle in sql:
                return [{"result": response, "status": "OK"}]
        return [{"result": [], "status": "OK"}]


class _StubPool:
    def __init__(self, responses: dict[str, list[dict]]):
        self._db = _StubDB(responses)

    @asynccontextmanager
    async def connection(self):
        yield self._db


@pytest.mark.asyncio
async def test_aggregator_returns_metric_keys():
    from core.engine.contributions.aggregator import compute_contributions

    pool = _StubPool({})
    result = await compute_contributions(pool, "product:platform")
    assert {
        "prs_reviewed",
        "gaps_caught",
        "you_shipped",
        "we_let_go",
        "effectiveness",
        "tasks_completed",
        "cost_saved_usd",
    }.issubset(set(result["metrics"].keys()))


@pytest.mark.asyncio
async def test_aggregator_headline_contains_partner_voice():
    """Headline must mention ACE + use partner-voice pronoun (we/our/us)."""
    from core.engine.contributions.aggregator import compute_contributions

    pool = _StubPool({"token_ledger_entry": [{"id": "tl:1", "cost_usd": 0.01, "cache_read_tokens": 100}] * 5})
    result = await compute_contributions(pool, "product:platform")
    headline = result["headline"].lower()
    assert any(w in headline for w in ("we", "our", "us"))
    assert len(headline) >= 50


@pytest.mark.asyncio
async def test_aggregator_isolates_subquery_failures():
    """If pr_review query raises, that metric returns null but others still populate."""
    from core.engine.contributions.aggregator import compute_contributions

    class _FailingDB(_StubDB):
        async def query(self, sql: str, params=None):
            if "pr_review" in sql:
                raise RuntimeError("simulated table missing")
            return await super().query(sql, params)

    class _FailingPool(_StubPool):
        @asynccontextmanager
        async def connection(self):
            yield _FailingDB({})

    result = await compute_contributions(_FailingPool({}), "product:platform")
    assert result["metrics"]["prs_reviewed"]["count"] is None
    # Other metrics still present
    assert result["metrics"]["gaps_caught"]["count"] == 0


@pytest.mark.asyncio
async def test_token_ledger_query_scopes_to_executor_rows():
    """tasks_completed / cost_saved_usd must not count per-call provider rows
    (source="cli_provider"/"openai_compat", Task 4c): raw LLM calls are not
    "tasks we ran", and their cache reads would double-count savings the
    executor accumulator row already reports. Legacy rows (no source field)
    stay in via the NONE/IS NULL hedge."""
    from core.engine.contributions.aggregator import compute_contributions

    captured: list[str] = []

    class _CapturingDB(_StubDB):
        async def query(self, sql: str, params: dict | None = None):
            captured.append(sql)
            return await super().query(sql, params)

    pool = _StubPool({})
    pool._db = _CapturingDB({})

    await compute_contributions(pool, "product:platform")

    ledger_sql = next(s for s in captured if "token_ledger_entry" in s)
    assert "(source = NONE OR source IS NULL OR source = 'executor')" in ledger_sql


@pytest.mark.asyncio
async def test_token_ledger_query_field_names_match_record_write_shape():
    """The ledger query must read the fields TokenLedger.record() actually
    writes — `product` as a record link, `resolved_at`, and cache reads nested
    at tokens_by_stage.cache_read. The prior product_id / created_at /
    cache_read_tokens read matched ZERO rows by construction, making the
    tasks/cost metrics permanently 0. Asserted against record()'s CREATE
    statement so the two can't drift apart silently again."""
    import re

    from core.engine.contributions.aggregator import compute_contributions

    captured: list[str] = []

    class _CapturingDB(_StubDB):
        async def query(self, sql: str, params: dict | None = None):
            captured.append(sql)
            return await super().query(sql, params)

    pool = _StubPool({})
    pool._db = _CapturingDB({})
    await compute_contributions(pool, "product:platform")
    ledger_sql = next(s for s in captured if "token_ledger_entry" in s)

    # Capture what record() writes, through the same query-capturing trick.
    from unittest.mock import AsyncMock, MagicMock, patch

    from core.engine.intelligence.token_ledger import TokenLedger

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[])
    mock_conn = MagicMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_db)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    with patch("core.engine.intelligence.token_ledger.pool") as mock_pool:
        mock_pool.connection.return_value = mock_conn
        await TokenLedger().record(
            task_id="t",
            discipline="d",
            task_type="tt",
            tier="",
            executor_model="m",
            reviewer_model=None,
            passes=1,
            escalated=False,
            cost_usd=0.0,
            tokens_by_stage={},
            cache_hit_rate=0.0,
            failure_categories=[],
        )
    write_sql = mock_db.query.call_args.args[0]
    written_fields = set(re.findall(r"(\w+)\s*=\s*", write_sql))

    # Every field the aggregator filters/selects on must be one record() writes
    # (tokens_by_stage.cache_read reads INTO a written nested object).
    assert "product" in written_fields and "WHERE product = <record>$pid" in ledger_sql
    assert "resolved_at" in written_fields and "resolved_at" in ledger_sql
    assert "tokens_by_stage" in written_fields and "tokens_by_stage.cache_read" in ledger_sql
    # The dead field names must be gone.
    assert "product_id" not in ledger_sql
    assert "created_at" not in ledger_sql
