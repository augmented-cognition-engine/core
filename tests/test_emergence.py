# tests/test_emergence.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_no_emergence_below_threshold():
    """No specialty created when fewer than 5 unparented insights in a subdomain."""
    from core.engine.intelligence.emergence import check_emergence

    with patch("core.engine.intelligence.emergence.default_pool") as mock_pool:
        mock_conn = AsyncMock()
        # 3 unparented insights — below threshold
        mock_conn.query = AsyncMock(return_value=[[{"count": 3, "source_domain": "architecture"}]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await check_emergence("product:test")

    assert result == []


@pytest.mark.asyncio
async def test_emergence_triggers_at_threshold():
    """Specialty created when 5+ unparented insights cluster in a subdomain."""
    from core.engine.intelligence.emergence import check_emergence

    mock_insights = [{"id": f"insight:{i}", "content": f"Token fact {i}", "source_domain": "ux"} for i in range(5)]

    mock_llm_response = {"name": "Token Pipeline", "slug": "token-pipeline"}

    with patch("core.engine.intelligence.emergence.default_pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(
            side_effect=[
                # First call: count unparented insights per subdomain
                [[{"count": 5, "source_domain": "ux"}]],
                # Second call: fetch the actual insights for LLM
                [mock_insights],
                # Third call: recheck eligibility after the LLM await
                [mock_insights],
                # Fourth call: create specialty
                [[{"id": "specialty:abc"}]],
                # Fifth call: update insights
                [[]],
            ]
        )
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("core.engine.intelligence.emergence.llm") as mock_llm:
            mock_llm.complete_json = AsyncMock(return_value=mock_llm_response)
            result = await check_emergence("product:test")

    assert len(result) == 1
    assert result[0]["slug"] == "token-pipeline"


@pytest.mark.asyncio
async def test_emergence_skips_if_specialty_exists():
    """No duplicate specialty if one already exists for this cluster."""
    from core.engine.intelligence.emergence import check_emergence

    with patch("core.engine.intelligence.emergence.default_pool") as mock_pool:
        mock_conn = AsyncMock()
        # Count returns empty (0 unparented)
        mock_conn.query = AsyncMock(return_value=[[]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await check_emergence("product:test")

    assert result == []


@pytest.mark.asyncio
async def test_disabled_emergence_performs_no_database_or_model_work(monkeypatch):
    from core.engine.intelligence.emergence import check_emergence

    caller_pool = MagicMock()
    monkeypatch.setattr("core.engine.intelligence.emergence.settings.emergence_enabled", False)
    with patch("core.engine.intelligence.emergence.llm") as mock_llm:
        assert await check_emergence("product:test", pool=caller_pool) == []

    caller_pool.connection.assert_not_called()
    mock_llm.complete_json.assert_not_called()


@pytest.mark.asyncio
async def test_emergence_uses_caller_pool_and_releases_connection_for_model(monkeypatch):
    from contextlib import asynccontextmanager

    from core.engine.intelligence.emergence import check_emergence

    insights = [{"id": f"insight:{index}", "content": f"Fact {index}"} for index in range(5)]

    class TrackingDB:
        async def query(self, statement, params=None):
            assert (params or {}).get("product") == "product:caller"
            if "count() AS count" in statement:
                return [{"count": 5, "source_domain": "architecture"}]
            if "SELECT id, content" in statement or "SELECT id\n" in statement:
                return insights
            if "CREATE specialty" in statement:
                return [{"id": "specialty:caller"}]
            return []

    class TrackingPool:
        def __init__(self):
            self.active = 0
            self.connection_count = 0
            self.db = TrackingDB()

        @asynccontextmanager
        async def connection(self):
            self.connection_count += 1
            self.active += 1
            try:
                yield self.db
            finally:
                self.active -= 1

    caller_pool = TrackingPool()

    async def complete_json(*args, **kwargs):
        assert caller_pool.active == 0
        return {"name": "Architecture", "slug": "architecture"}

    monkeypatch.setattr("core.engine.intelligence.emergence.settings.emergence_enabled", True)
    with (
        patch("core.engine.intelligence.emergence.default_pool") as global_pool,
        patch("core.engine.intelligence.emergence.llm.complete_json", new=complete_json),
    ):
        result = await check_emergence("product:caller", pool=caller_pool)

    assert result == [
        {
            "id": "specialty:caller",
            "name": "Architecture",
            "slug": "architecture",
            "domain_hint": "architecture",
        }
    ]
    assert caller_pool.connection_count == 2
    assert caller_pool.active == 0
    global_pool.connection.assert_not_called()
