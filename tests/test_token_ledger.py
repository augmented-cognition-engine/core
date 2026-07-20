from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_record_writes_to_db():
    from core.engine.intelligence.token_ledger import TokenLedger

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[])
    mock_conn = MagicMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_db)
    mock_conn.__aexit__ = AsyncMock(return_value=False)

    with patch("core.engine.intelligence.token_ledger.pool") as mock_pool:
        mock_pool.connection.return_value = mock_conn
        ledger = TokenLedger()
        await ledger.record(
            task_id="task:abc",
            discipline="coding",
            task_type="implementation",
            tier="moderate",
            executor_model="claude-sonnet-4-6",
            reviewer_model="claude-sonnet-4-6",
            passes=2,
            escalated=False,
            cost_usd=0.0045,
            tokens_by_stage={"classification": 200, "execution": 1800},
            cache_hit_rate=0.6,
            failure_categories=["missing_edge_case"],
        )

    mock_db.query.assert_called_once()
    sql, params = mock_db.query.call_args[0]
    assert "CREATE token_ledger_entry" in sql
    assert params["task_id"] == "task:abc"
    assert params["discipline"] == "coding"
    assert params["passes"] == 2
    assert params["escalated"] is False


@pytest.mark.asyncio
async def test_record_is_non_fatal_on_db_error():
    from core.engine.intelligence.token_ledger import TokenLedger

    mock_conn = MagicMock()
    mock_conn.__aenter__ = AsyncMock(side_effect=Exception("db down"))
    mock_conn.__aexit__ = AsyncMock(return_value=False)

    with patch("core.engine.intelligence.token_ledger.pool") as mock_pool:
        mock_pool.connection.return_value = mock_conn
        ledger = TokenLedger()
        await ledger.record(
            task_id="task:xyz",
            discipline="coding",
            task_type="implementation",
            tier="simple",
            executor_model="claude-haiku-4-5-20251001",
            reviewer_model="claude-sonnet-4-6",
            passes=1,
            escalated=False,
            cost_usd=0.001,
            tokens_by_stage={},
            cache_hit_rate=0.0,
            failure_categories=[],
        )


@pytest.mark.asyncio
async def test_get_summary_returns_dict():
    from core.engine.intelligence.token_ledger import TokenLedger

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[])
    mock_conn = MagicMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_db)
    mock_conn.__aexit__ = AsyncMock(return_value=False)

    with patch("core.engine.intelligence.token_ledger.pool") as mock_pool:
        mock_pool.connection.return_value = mock_conn
        with patch("core.engine.intelligence.token_ledger.parse_rows") as mock_parse:
            mock_parse.return_value = [
                {
                    "avg_cost_usd": 0.003,
                    "avg_passes": 1.5,
                    "avg_cache_hit_rate": 0.6,
                    "total_tasks": 20,
                    "escalated_count": 1,
                }
            ]
            ledger = TokenLedger()
            result = await ledger.get_summary(product_id="product:test", days=30)

    assert "avg_cost_usd" in result
    assert result["avg_passes"] == 1.5
    assert "escalation_rate" in result


@pytest.mark.asyncio
async def test_aggregations_scope_to_executor_rows():
    """get_summary / get_passes_by_discipline / get_weekly_trend aggregate
    task-level executor rows ONLY — per-call provider rows (cli_provider /
    openai_compat, Task 4c) describe the same underlying spend the executor
    accumulator summarizes, so mixing double-counts cost and reports raw LLM
    calls as tasks. Legacy pre-source rows stay in via `source = NONE`.
    get_failure_categories needs no filter: provider rows always write [] and
    the array::len > 0 predicate already excludes them structurally."""
    from core.engine.intelligence.token_ledger import TokenLedger

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[])
    mock_conn = MagicMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_db)
    mock_conn.__aexit__ = AsyncMock(return_value=False)

    with patch("core.engine.intelligence.token_ledger.pool") as mock_pool:
        mock_pool.connection.return_value = mock_conn
        ledger = TokenLedger()
        await ledger.get_summary("product:platform")
        await ledger.get_passes_by_discipline("product:platform")
        await ledger.get_weekly_trend("product:platform")
        await ledger.get_failure_categories("product:platform")

    sqls = [call.args[0] for call in mock_db.query.call_args_list]
    scope = "(source = NONE OR source IS NULL OR source = 'executor')"
    assert scope in sqls[0], "get_summary must scope to executor rows"
    assert scope in sqls[1], "get_passes_by_discipline must scope to executor rows"
    assert scope in sqls[2], "get_weekly_trend must scope to executor rows"
    assert scope not in sqls[3], "failure categories are structurally executor-only"
