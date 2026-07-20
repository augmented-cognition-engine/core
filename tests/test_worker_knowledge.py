# tests/test_worker_knowledge.py
"""Tests for DisciplineKnowledgeAgent — Phase 6 of the ACE Worker Service."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.engine.worker.knowledge import DisciplineKnowledgeAgent, _corpus_cache


@pytest.fixture(autouse=True)
def clear_cache():
    """Reset in-memory corpus cache between tests."""
    _corpus_cache.clear()
    yield
    _corpus_cache.clear()


# ---------------------------------------------------------------------------
# TTL behaviour
# ---------------------------------------------------------------------------


@pytest.fixture
def agent():
    return DisciplineKnowledgeAgent()


# ---------------------------------------------------------------------------
# build_corpus
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_corpus_returns_empty_on_db_failure(agent):
    """DB failure must return '' — agent must not raise."""
    with patch("core.engine.worker.knowledge.pool") as mock_pool:
        mock_pool.connection.side_effect = Exception("DB down")
        result = await agent.build_corpus("ux", "product:test")
    assert result == ""


@pytest.mark.asyncio
async def test_build_corpus_includes_decisions_section(agent):
    """When decisions exist, corpus must contain a Decisions section."""
    # build_corpus runs 3 queries: insights (1), decisions (2), capabilities (3).
    # parse_rows is called once per query result.
    mock_decisions = [{"title": "Dense Glass aesthetic", "rationale": "Premium, restrained", "annotation": ""}]
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=MagicMock())
    mock_context = AsyncMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_db)
    mock_context.__aexit__ = AsyncMock(return_value=False)

    call_index = [0]

    def parse_rows_side_effect(result):
        call_index[0] += 1
        # query 1 = insights (empty), query 2 = decisions (populated), query 3 = capabilities (empty)
        return mock_decisions if call_index[0] == 2 else []

    with (
        patch("core.engine.worker.knowledge.pool") as mock_pool,
        patch("core.engine.worker.knowledge.parse_rows", side_effect=parse_rows_side_effect),
    ):
        mock_pool.connection.return_value = mock_context
        result = await agent.build_corpus("ux", "product:test")

    assert "Design Decisions" in result and "Dense Glass" in result


@pytest.mark.asyncio
async def test_build_corpus_returns_empty_when_no_data(agent):
    """When DB returns no rows for any query, corpus must be empty string."""
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=MagicMock())
    mock_context = AsyncMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_db)
    mock_context.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("core.engine.worker.knowledge.pool") as mock_pool,
        patch("core.engine.worker.knowledge.parse_rows", return_value=[]),
    ):
        mock_pool.connection.return_value = mock_context
        result = await agent.build_corpus("ux", "product:test")

    assert result == ""


@pytest.mark.asyncio
async def test_build_corpus_caps_at_max_chars(agent):
    """Corpus must be hard-capped at _MAX_CORPUS_CHARS to protect token budget."""
    from core.engine.worker.knowledge import _MAX_CORPUS_CHARS

    huge_decision = [{"title": "Big decision", "rationale": "x" * 10000, "annotation": ""}]
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=MagicMock())
    mock_context = AsyncMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_db)
    mock_context.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("core.engine.worker.knowledge.pool") as mock_pool,
        patch("core.engine.worker.knowledge.parse_rows", return_value=huge_decision),
    ):
        mock_pool.connection.return_value = mock_context
        result = await agent.build_corpus("ux", "product:test")

    assert len(result) <= _MAX_CORPUS_CHARS


# ---------------------------------------------------------------------------
# prime
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prime_stores_corpus_in_cache(agent):
    """prime() must store the built corpus in _corpus_cache."""
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=MagicMock())
    mock_context = AsyncMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_db)
    mock_context.__aexit__ = AsyncMock(return_value=False)

    decisions = [{"title": "Test decision", "rationale": "Good reason", "annotation": ""}]

    call_count = 0

    def parse_rows_side_effect(result):
        nonlocal call_count
        call_count += 1
        return decisions if call_count == 2 else []  # return on 2nd query call

    with (
        patch("core.engine.worker.knowledge.pool") as mock_pool,
        patch("core.engine.worker.knowledge.parse_rows", side_effect=parse_rows_side_effect),
    ):
        mock_pool.connection.return_value = mock_context
        corpus = await agent.prime("ux", "product:test")

    # Either corpus was built (and cached) or empty (no rows) — cache state must be consistent.
    # Cache stores (corpus_text, timestamp) tuples since TTL was added.
    if corpus:
        assert ("ux", "product:test") in _corpus_cache
        cached_text, cached_at = _corpus_cache[("ux", "product:test")]
        assert cached_text == corpus
        assert cached_at > 0
    else:
        assert ("ux", "product:test") not in _corpus_cache


@pytest.mark.asyncio
async def test_prime_returns_empty_when_no_data(agent):
    """prime() must return '' and not cache empty string when no data."""
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=MagicMock())
    mock_context = AsyncMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_db)
    mock_context.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("core.engine.worker.knowledge.pool") as mock_pool,
        patch("core.engine.worker.knowledge.parse_rows", return_value=[]),
    ):
        mock_pool.connection.return_value = mock_context
        corpus = await agent.prime("ux", "product:test")

    assert corpus == ""
    assert ("ux", "product:test") not in _corpus_cache


# ---------------------------------------------------------------------------
# query
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_query_reprimes_on_ttl_expiry(agent):
    """When cache entry is past _CORPUS_TTL, query() must re-prime rather than serve stale data."""

    # Seed cache with an expired entry. The staleness check (knowledge.py) uses
    # time.monotonic(), whose zero point is system BOOT — not the Unix epoch. A
    # bare 0.0 is "boot time", which is only past the 600s TTL once the host has
    # been up > 10 min: green on any dev box, RED on a freshly-booted CI runner.
    # Seed relative to the monotonic clock so it is expired regardless of uptime.
    import time

    stale_text = "## Old Design Decisions\n- Stale decision"
    expired_at = time.monotonic() - 10_000  # well past _CORPUS_TTL (600s), any uptime
    _corpus_cache[("ux", "product:test")] = (stale_text, expired_at)

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=MagicMock())
    mock_context = AsyncMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_db)
    mock_context.__aexit__ = AsyncMock(return_value=False)

    fresh_decision = [{"title": "Fresh decision", "rationale": "Updated reasoning", "annotation": ""}]
    call_index = [0]

    def parse_rows_side_effect(result):
        call_index[0] += 1
        return fresh_decision if call_index[0] == 2 else []

    mock_llm = MagicMock()
    mock_llm.complete = AsyncMock(return_value="Fresh decision is: Updated reasoning.")

    with (
        patch("core.engine.worker.knowledge.pool") as mock_pool,
        patch("core.engine.worker.knowledge.parse_rows", side_effect=parse_rows_side_effect),
        patch("core.engine.core.llm.get_llm", return_value=mock_llm),
    ):
        mock_pool.connection.return_value = mock_context
        result = await agent.query("ux", "what is the current direction?", "product:test")

    # Cache must have been refreshed — timestamp should no longer be the stale one
    assert ("ux", "product:test") in _corpus_cache
    _, new_ts = _corpus_cache[("ux", "product:test")]
    assert new_ts > expired_at  # refreshed


@pytest.mark.asyncio
async def test_query_returns_no_data_message_when_corpus_empty(agent):
    """When corpus is empty (no data in DB), query must return a clear 'no data' message."""
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=MagicMock())
    mock_context = AsyncMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_db)
    mock_context.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("core.engine.worker.knowledge.pool") as mock_pool,
        patch("core.engine.worker.knowledge.parse_rows", return_value=[]),
    ):
        mock_pool.connection.return_value = mock_context
        result = await agent.query("ux", "what decisions were made?", "product:test")

    # Sentinel: must contain discipline name and a clear 'no data' signal
    assert "ux" in result
    assert "No accumulated intelligence" in result or "no" in result.lower()


@pytest.mark.asyncio
async def test_query_calls_llm_with_corpus_context(agent):
    """When corpus exists, query must call LLM with corpus in system prompt."""
    import time

    _corpus_cache[("ux", "product:test")] = (
        "## Design Decisions\n- Dense Glass: dark, restrained aesthetic",
        time.monotonic(),
    )

    mock_llm = MagicMock()
    mock_llm.complete = AsyncMock(return_value="The locked direction is Dense Glass — dark and restrained.")

    with patch("core.engine.core.llm.get_llm", return_value=mock_llm):
        result = await agent.query("ux", "what is the locked direction?", "product:test")

    mock_llm.complete.assert_called_once()
    call_kwargs = mock_llm.complete.call_args
    assert "Dense Glass" in result or "dense glass" in result.lower()


@pytest.mark.asyncio
async def test_query_falls_back_gracefully_on_llm_failure(agent):
    """LLM failure must return a corpus summary, not raise or return empty."""
    import time

    _corpus_cache[("ux", "product:test")] = (
        "## Design Decisions\n- Dense Glass aesthetic locked",
        time.monotonic(),
    )

    mock_llm = MagicMock()
    mock_llm.complete = AsyncMock(side_effect=Exception("LLM timeout"))

    with patch("core.engine.core.llm.get_llm", return_value=mock_llm):
        result = await agent.query("ux", "what design decisions were made?", "product:test")

    # Sentinel: must return something meaningful even on LLM failure
    assert len(result) > 0
    assert "Dense Glass" in result or "Corpus summary" in result or "corpus" in result.lower()
