"""Active-loop write-back (2.2) — a completed reasoning conclusion is persisted as a graph
observation so the synthesizer turns it into a retrievable insight. Fake pool, no real DB."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.engine.orchestration import executor

_LONG = (
    "Adopt a curated marketplace with a mandatory review gate — it balances ecosystem reach against "
    "the trust and security risk an open marketplace would create."
)


def _req():
    return type("Req", (), {"product_id": "product:platform"})()


def _capturing_pool(captured):
    db = MagicMock()

    async def _query(sql, params=None):
        captured.append((sql, params))
        return [[]]

    db.query = AsyncMock(side_effect=_query)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=db)
    ctx.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.connection.return_value = ctx
    return pool


@pytest.mark.asyncio
async def test_substantive_conclusion_writes_an_observation():
    captured: list = []
    with patch("core.engine.core.db.pool", _capturing_pool(captured)):
        await executor._capture_conclusion_to_graph(_req(), {"discipline": "strategy"}, _LONG, "complete")
    assert len(captured) == 1
    sql, params = captured[0]
    assert "CREATE observation" in sql
    assert "source = 'reasoning_conclusion'" in sql
    assert "status = 'pending'" in sql  # picked up by the synthesizer
    assert params["product"] == "product:platform"
    assert params["discipline"] == "strategy"
    assert _LONG[:50] in params["content"]


@pytest.mark.asyncio
async def test_short_conclusion_is_noise_gated():
    captured: list = []
    with patch("core.engine.core.db.pool", _capturing_pool(captured)):
        await executor._capture_conclusion_to_graph(_req(), {"discipline": "strategy"}, "ok.", "complete")
    assert captured == []  # below _MIN_CONCLUSION_CHARS → no graph write


@pytest.mark.asyncio
async def test_failed_run_is_not_persisted():
    captured: list = []
    with patch("core.engine.core.db.pool", _capturing_pool(captured)):
        await executor._capture_conclusion_to_graph(_req(), {"discipline": "strategy"}, _LONG, "failed")
    assert captured == []  # status != complete → no graph write


@pytest.mark.asyncio
async def test_falls_back_to_domain_path_for_discipline():
    captured: list = []
    with patch("core.engine.core.db.pool", _capturing_pool(captured)):
        await executor._capture_conclusion_to_graph(_req(), {"domain_path": "security.appsec"}, _LONG, "complete")
    # Normalized to the bare discipline slug so the worker/synthesizer dedup keys match (not the dotted path).
    assert captured[0][1]["discipline"] == "security"


@pytest.mark.asyncio
async def test_db_failure_is_non_fatal():
    pool = MagicMock()
    pool.connection.side_effect = Exception("DB down")
    with patch("core.engine.core.db.pool", pool):
        await executor._capture_conclusion_to_graph(_req(), {"discipline": "strategy"}, _LONG, "complete")  # no raise


@pytest.mark.asyncio
async def test_writeback_runs_even_when_ledger_create_returns_none():
    """Reachability: the active loop must NOT be coupled to the event-log write. When create_run
    short-circuits (returns None), _record_reasoning_run early-returns from its try — the conclusion
    write-back still fires because it's in a `finally`. (Caught by adversarial review; the per-helper
    tests above can't see this coupling because they call the helper directly.)"""
    spy = AsyncMock()
    with (
        patch.object(executor, "_capture_conclusion_to_graph", spy),
        patch("core.engine.cognition.run_ledger.create_run", AsyncMock(return_value=None)),
    ):
        await executor._record_reasoning_run(
            _req(),
            {"discipline": "strategy"},
            depth=3,
            meta_skills=[],
            phases=[],
            conclusion=_LONG,
            status="complete",
        )
    spy.assert_awaited_once()


@pytest.mark.asyncio
async def test_writeback_runs_even_when_ledger_raises():
    """Same guarantee on the except path: a thrown ledger write can't suppress the active loop."""
    spy = AsyncMock()
    with (
        patch.object(executor, "_capture_conclusion_to_graph", spy),
        patch("core.engine.cognition.run_ledger.create_run", AsyncMock(side_effect=Exception("ledger down"))),
    ):
        await executor._record_reasoning_run(
            _req(),
            {"discipline": "strategy"},
            depth=3,
            meta_skills=[],
            phases=[],
            conclusion=_LONG,
            status="complete",
        )
    spy.assert_awaited_once()
