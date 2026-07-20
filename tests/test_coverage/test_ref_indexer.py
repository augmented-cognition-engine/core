"""Tests for ref_indexer: is_test_path and has_test_reference DB path."""

import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.engine.intelligence.ref_indexer import has_test_reference, is_test_path


def _make_mock_pool(rows_return):
    """Build a mock pool that yields a mock db returning rows_return from query."""
    mock_conn = AsyncMock()
    mock_conn.query = AsyncMock(return_value=[[]])

    @contextlib.asynccontextmanager
    async def _connection():
        yield mock_conn

    mock_pool = MagicMock()
    mock_pool.connection = _connection
    return mock_pool, mock_conn


# ── is_test_path ───────────────────────────────────────────────────────────


def test_is_test_path_tests_prefix():
    assert is_test_path("tests/test_foo.py")


def test_is_test_path_test_underscore_prefix():
    assert is_test_path("src/test_bar.py")


def test_is_test_path_test_suffix():
    assert is_test_path("src/foo_test.py")


def test_is_test_path_tests_subdir():
    assert is_test_path("engine/tests/test_x.py")


def test_is_test_path_source_file_is_false():
    assert not is_test_path("core/engine/product/enforcer.py")


def test_is_test_path_empty_string():
    assert not is_test_path("")


# ── has_test_reference — DB available ─────────────────────────────────────


@pytest.mark.asyncio
async def test_has_test_reference_true_when_refs_non_empty():
    mock_pool, _ = _make_mock_pool([])
    with (
        patch("core.engine.intelligence.ref_indexer.pool", mock_pool),
        patch(
            "core.engine.intelligence.ref_indexer.parse_rows", return_value=[{"test_refs": ["graph_function:abc123"]}]
        ),
    ):
        result = await has_test_reference("my_func", "engine/foo.py")
    assert result is True


@pytest.mark.asyncio
async def test_has_test_reference_false_when_refs_empty():
    mock_pool, _ = _make_mock_pool([])
    with (
        patch("core.engine.intelligence.ref_indexer.pool", mock_pool),
        patch("core.engine.intelligence.ref_indexer.parse_rows", return_value=[{"test_refs": []}]),
    ):
        result = await has_test_reference("my_func", "engine/foo.py")
    assert result is False


@pytest.mark.asyncio
async def test_has_test_reference_false_when_no_rows():
    mock_pool, _ = _make_mock_pool([])
    with (
        patch("core.engine.intelligence.ref_indexer.pool", mock_pool),
        patch("core.engine.intelligence.ref_indexer.parse_rows", return_value=[]),
    ):
        result = await has_test_reference("missing_func", "engine/foo.py")
    assert result is False


@pytest.mark.asyncio
async def test_has_test_reference_false_on_exception():
    """DB unavailable → returns False, never raises."""
    with patch("core.engine.intelligence.ref_indexer.pool") as mock_pool:
        mock_pool.connection.side_effect = RuntimeError("DB down")
        result = await has_test_reference("fn", "file.py")
    assert result is False
