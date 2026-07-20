"""Tests for docs generator: Mermaid fallback and section construction."""

import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.engine.generation.docs_generator import _minimal_mermaid, generate_architecture_diagram


def _make_pool(rows):
    mock_conn = AsyncMock()
    mock_conn.query = AsyncMock(return_value=[[]])

    @contextlib.asynccontextmanager
    async def _connection():
        yield mock_conn

    mock_pool = MagicMock()
    mock_pool.connection = _connection
    return mock_pool


# ── _minimal_mermaid ───────────────────────────────────────────────────────


def test_minimal_mermaid_starts_with_flowchart():
    result = _minimal_mermaid("product:test")
    assert result.startswith("flowchart")


def test_minimal_mermaid_contains_slug():
    result = _minimal_mermaid("product:my_product")
    assert "my_product" in result


# ── generate_architecture_diagram ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_architecture_diagram_fallback_on_no_caps():
    mock_pool = _make_pool([])
    with (
        patch("core.engine.generation.docs_generator.pool", mock_pool),
        patch("core.engine.generation.docs_generator.parse_rows", return_value=[]),
    ):
        result = await generate_architecture_diagram("product:test")
    assert "flowchart" in result or "graph" in result


@pytest.mark.asyncio
async def test_generate_architecture_diagram_returns_string():
    mock_pool = _make_pool([])
    caps = [{"slug": "auth", "name": "Auth", "category": "core"}]
    with (
        patch("core.engine.generation.docs_generator.pool", mock_pool),
        patch("core.engine.generation.docs_generator.parse_rows", return_value=caps),
    ):
        result = await generate_architecture_diagram("product:test")
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_generate_architecture_diagram_db_failure_returns_minimal():
    with patch("core.engine.generation.docs_generator.pool") as mp:
        mp.connection.side_effect = RuntimeError("DB down")
        result = await generate_architecture_diagram("product:test")
    assert "flowchart" in result
