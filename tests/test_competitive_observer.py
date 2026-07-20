"""Tests for the competitive observer sentinel engine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

# --- fetch_source tests ---


@pytest.fixture
def mock_httpx(monkeypatch):
    """Mock httpx.AsyncClient for web fetching."""
    import httpx

    class MockResponse:
        def __init__(self, text, status_code=200):
            self.text = text
            self.status_code = status_code

        def raise_for_status(self):
            if self.status_code >= 400:
                raise httpx.HTTPStatusError("error", request=None, response=self)

    class MockClient:
        def __init__(self, **kwargs):
            self.response_text = "<html><body><h2>New Feature</h2><p>We shipped X</p></body></html>"

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, url, **kwargs):
            return MockResponse(self.response_text)

    monkeypatch.setattr(httpx, "AsyncClient", MockClient)
    return MockClient


@pytest.mark.asyncio
async def test_fetch_source_returns_text(mock_httpx):
    from core.engine.sentinel.engines.competitive_observer import fetch_source

    text = await fetch_source({"type": "changelog", "url": "https://example.com/changelog"})
    assert isinstance(text, str)
    assert len(text) > 0
    assert "New Feature" in text


@pytest.mark.asyncio
async def test_fetch_source_handles_failure(monkeypatch):
    import httpx

    class FailClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, url, **kwargs):
            raise Exception("connection refused")

    monkeypatch.setattr(httpx, "AsyncClient", FailClient)

    from core.engine.sentinel.engines.competitive_observer import fetch_source

    text = await fetch_source({"type": "changelog", "url": "https://example.com/fail"})
    assert text == ""


# --- extract_signals tests ---


@pytest.fixture
def mock_llm(monkeypatch):
    """Mock the LLM to return structured signal extraction."""
    from core.engine.sentinel.engines import competitive_observer as co_module

    mock = AsyncMock()
    mock.complete_json.return_value = {
        "signals": [
            {
                "title": "Linear Agent launched",
                "description": "Built-in AI agent that understands workspace context",
                "relevance": "overlap",
                "urgency": "high",
            },
            {
                "title": "Time in Status",
                "description": "Tracks cumulative time in each workflow status",
                "relevance": "gap",
                "urgency": "medium",
            },
        ]
    }
    monkeypatch.setattr(co_module, "llm", mock)
    return mock


@pytest.mark.asyncio
async def test_extract_signals_parses_llm_response(mock_llm):
    from core.engine.sentinel.engines.competitive_observer import extract_signals

    signals = await extract_signals(
        "Some changelog text about new features and improvements shipped this quarter", "Linear"
    )
    assert len(signals) == 2
    assert signals[0]["title"] == "Linear Agent launched"
    assert signals[0]["relevance"] == "overlap"
    assert signals[1]["urgency"] == "medium"


@pytest.mark.asyncio
async def test_extract_signals_handles_empty_text(mock_llm):
    from core.engine.sentinel.engines.competitive_observer import extract_signals

    signals = await extract_signals("", "Linear")
    assert signals == []


@pytest.mark.asyncio
async def test_extract_signals_handles_llm_failure(monkeypatch):
    from core.engine.sentinel.engines import competitive_observer as co_module

    mock = AsyncMock()
    mock.complete_json.side_effect = Exception("LLM unavailable")
    monkeypatch.setattr(co_module, "llm", mock)

    from core.engine.sentinel.engines.competitive_observer import extract_signals

    signals = await extract_signals("Some text", "Linear")
    assert signals == []


# --- classify_signal tests ---


@pytest.mark.asyncio
async def test_classify_signal_returns_enriched_signal(monkeypatch):
    from core.engine.sentinel.engines import competitive_observer as co_module

    mock = AsyncMock()
    mock.complete_json.return_value = {
        "relevance_score": 0.85,
        "action": "respond",
        "rationale": "This is a direct feature overlap with our briefing engine",
    }
    monkeypatch.setattr(co_module, "llm", mock)

    from core.engine.sentinel.engines.competitive_observer import classify_signal

    signal = {
        "title": "Pulse Audio Digests",
        "description": "Weekly audio summaries of project updates",
        "relevance": "gap",
        "urgency": "medium",
    }
    enriched = await classify_signal(signal)
    assert enriched["relevance_score"] == 0.85
    assert enriched["action"] == "respond"
    assert "rationale" in enriched


@pytest.mark.asyncio
async def test_classify_signal_defaults_on_failure(monkeypatch):
    from core.engine.sentinel.engines import competitive_observer as co_module

    mock = AsyncMock()
    mock.complete_json.side_effect = Exception("LLM down")
    monkeypatch.setattr(co_module, "llm", mock)

    from core.engine.sentinel.engines.competitive_observer import classify_signal

    signal = {"title": "Feature X", "description": "Does X", "relevance": "gap", "urgency": "low"}
    enriched = await classify_signal(signal)
    assert enriched["relevance_score"] == 0.5
    assert enriched["action"] == "monitor"


# --- should_scan tests ---


def test_should_scan_tier1_weekly():
    from core.engine.sentinel.engines.competitive_observer import should_scan

    now = datetime(2026, 3, 25, 6, 0, tzinfo=timezone.utc)
    assert should_scan({"tier": 1, "last_scanned": None}, now) is True
    assert should_scan({"tier": 1, "last_scanned": now - timedelta(days=8)}, now) is True
    assert should_scan({"tier": 1, "last_scanned": now - timedelta(days=2)}, now) is False


def test_should_scan_tier2_monthly():
    from core.engine.sentinel.engines.competitive_observer import should_scan

    now = datetime(2026, 3, 3, 6, 0, tzinfo=timezone.utc)
    assert should_scan({"tier": 2, "last_scanned": None}, now) is True
    assert should_scan({"tier": 2, "last_scanned": now - timedelta(days=30)}, now) is True
    assert should_scan({"tier": 2, "last_scanned": now - timedelta(days=10)}, now) is False


def test_should_scan_tier3_quarterly():
    from core.engine.sentinel.engines.competitive_observer import should_scan

    now = datetime(2026, 4, 6, 6, 0, tzinfo=timezone.utc)
    assert should_scan({"tier": 3, "last_scanned": None}, now) is True
    assert should_scan({"tier": 3, "last_scanned": now - timedelta(days=91)}, now) is True
    assert should_scan({"tier": 3, "last_scanned": now - timedelta(days=30)}, now) is False


# --- run_competitive_observer tests ---


@pytest.fixture
def mock_db(monkeypatch):
    """Mock the DB pool for engine tests."""
    mock_conn = AsyncMock()

    competitor_row = {
        "id": "competitor:linear",
        "name": "Linear",
        "tier": 1,
        "sources": [{"type": "changelog", "url": "https://linear.app/changelog"}],
        "domains": ["product.project-management"],
        "last_scanned": None,
    }

    call_count = 0

    async def _query_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return [competitor_row]
        return []

    mock_conn.query = AsyncMock(side_effect=_query_side_effect)

    mock_pool = MagicMock()
    mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)

    # Patch both the source module AND the engine module. competitive_observer.py
    # does `from engine.core.db import pool`, which binds its own module-level name.
    # Patching only engine.core.db.pool leaves the already-imported reference live,
    # which then connects to the real SurrealDB and breaks environments without it.
    from core.engine.core import db as db_module
    from core.engine.sentinel.engines import competitive_observer as co_module

    monkeypatch.setattr(db_module, "pool", mock_pool)
    monkeypatch.setattr(co_module, "pool", mock_pool)
    return mock_conn


@pytest.mark.asyncio
async def test_run_engine_processes_competitors(mock_db, mock_httpx, mock_llm, monkeypatch):
    from core.engine.sentinel.engines import competitive_observer as co_module

    mock_write = AsyncMock(return_value="insight:new1")
    monkeypatch.setattr(co_module, "write_engine_insight", mock_write)

    async def mock_classify(signal):
        signal["relevance_score"] = 0.8
        signal["action"] = "respond"
        signal["rationale"] = "test"
        return signal

    monkeypatch.setattr(co_module, "classify_signal", mock_classify)

    mock_dispatch = AsyncMock(return_value={})
    monkeypatch.setattr(co_module, "_dispatch_alert", mock_dispatch)

    result = await co_module.run_competitive_observer("product:default", budget=10)

    assert result["competitors_scanned"] >= 0
    assert "signals_extracted" in result
    assert "insights_written" in result
