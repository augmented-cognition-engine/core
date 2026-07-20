"""Tests for error_explainer: traceback parsing, FIX extraction, and explain_error pipeline."""

import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.engine.intelligence.error_explainer import (
    ErrorContext,
    _extract_fix_commands,
    parse_traceback,
)

# ── parse_traceback ────────────────────────────────────────────────────────


SIMPLE_TB = """\
Traceback (most recent call last):
  File "/app/main.py", line 42, in handler
    result = process(data)
  File "/app/process.py", line 17, in process
    raise ValueError("bad input")
ValueError: bad input
"""

SINGLE_FILE_TB = """\
Traceback (most recent call last):
  File "/app/utils.py", line 5, in run
    1/0
ZeroDivisionError: division by zero
"""

NO_FILE_TB = "RuntimeError: something went wrong"


def test_parse_traceback_extracts_files():
    result = parse_traceback(SIMPLE_TB)
    assert len(result["files"]) == 2


def test_parse_traceback_file_paths():
    result = parse_traceback(SIMPLE_TB)
    paths = [f["path"] for f in result["files"]]
    assert "/app/main.py" in paths
    assert "/app/process.py" in paths


def test_parse_traceback_line_numbers():
    result = parse_traceback(SIMPLE_TB)
    assert result["files"][0]["line"] == 42
    assert result["files"][1]["line"] == 17


def test_parse_traceback_error_type():
    result = parse_traceback(SIMPLE_TB)
    assert result["error_type"] == "ValueError"


def test_parse_traceback_error_message():
    result = parse_traceback(SIMPLE_TB)
    assert result["error_message"] == "bad input"


def test_parse_traceback_innermost_is_last_file():
    result = parse_traceback(SIMPLE_TB)
    assert result["innermost"]["path"] == "/app/process.py"
    assert result["innermost"]["line"] == 17


def test_parse_traceback_single_file():
    result = parse_traceback(SINGLE_FILE_TB)
    assert len(result["files"]) == 1
    assert result["error_type"] == "ZeroDivisionError"


def test_parse_traceback_no_files_innermost_none():
    result = parse_traceback(NO_FILE_TB)
    assert result["files"] == []
    assert result["innermost"] is None


def test_parse_traceback_no_files_error_type():
    result = parse_traceback(NO_FILE_TB)
    assert result["error_type"] == "RuntimeError"
    assert result["error_message"] == "something went wrong"


def test_parse_traceback_no_colon_in_last_line():
    result = parse_traceback("SomeError")
    assert result["error_type"] == "SomeError"
    assert result["error_message"] == ""


# ── _extract_fix_commands ──────────────────────────────────────────────────


def test_extract_fix_commands_finds_fix_prefix():
    text = "The error is X.\nFIX: pip install openssl\nFIX: restart service"
    cmds = _extract_fix_commands(text)
    assert "pip install openssl" in cmds
    assert "restart service" in cmds


def test_extract_fix_commands_strips_prefix():
    text = "FIX: do something"
    cmds = _extract_fix_commands(text)
    assert cmds == ["do something"]


def test_extract_fix_commands_empty_when_no_fix():
    text = "Just an explanation without any fix lines."
    assert _extract_fix_commands(text) == []


def test_extract_fix_commands_ignores_non_fix_lines():
    text = "line1\nFIX: fix this\nline3"
    cmds = _extract_fix_commands(text)
    assert len(cmds) == 1
    assert cmds[0] == "fix this"


def test_extract_fix_commands_strips_whitespace():
    text = "FIX:   command with spaces   "
    cmds = _extract_fix_commands(text)
    assert cmds == ["command with spaces"]


# ── explain_error helpers ──────────────────────────────────────────────────


def _make_db_pool():
    mock_conn = AsyncMock()
    mock_conn.query = AsyncMock(return_value=[[]])

    @contextlib.asynccontextmanager
    async def _connection():
        yield mock_conn

    mock_pool = MagicMock()
    mock_pool.connection = _connection
    return mock_pool


async def _run_explain(error_text: str, llm_response: str = "ok"):
    """Run explain_error with all external deps patched out."""
    from core.engine.intelligence.error_explainer import explain_error

    mock_pool = _make_db_pool()
    mock_llm = MagicMock()
    mock_llm.complete = AsyncMock(return_value=llm_response)

    with (
        patch("core.engine.core.db.pool", mock_pool),
        patch("core.engine.core.db.parse_rows", return_value=[]),
        patch("core.engine.core.db.parse_one", return_value=None),
        patch("core.engine.core.llm.get_llm", return_value=mock_llm),
        patch("core.engine.intelligence.error_explainer._check_runbook", AsyncMock(return_value=None)),
        patch("core.engine.intelligence.error_explainer._capture_as_runbook", AsyncMock()),
    ):
        return await explain_error(error_text)


# ── explain_error ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_explain_error_returns_error_context():
    result = await _run_explain(SIMPLE_TB)
    assert isinstance(result, ErrorContext)


@pytest.mark.asyncio
async def test_explain_error_populates_error_type():
    result = await _run_explain(SIMPLE_TB)
    assert result.error_type == "ValueError"


@pytest.mark.asyncio
async def test_explain_error_populates_fix_commands():
    result = await _run_explain(SIMPLE_TB, llm_response="Explanation.\nFIX: pip install fix-pkg")
    assert "pip install fix-pkg" in result.fix_commands


@pytest.mark.asyncio
async def test_explain_error_traceback_files_populated():
    result = await _run_explain(SIMPLE_TB)
    assert "/app/process.py" in result.traceback_files


@pytest.mark.asyncio
async def test_explain_error_innermost_line():
    result = await _run_explain(SIMPLE_TB)
    assert result.innermost_line == 17


@pytest.mark.asyncio
async def test_explain_error_never_raises_on_db_failure():
    """Pipeline degrades gracefully when DB is unavailable."""
    from core.engine.intelligence.error_explainer import explain_error

    mock_pool = MagicMock()
    mock_pool.connection.side_effect = RuntimeError("db down")

    with (
        patch("core.engine.core.db.pool", mock_pool),
        patch("core.engine.core.db.parse_rows", side_effect=RuntimeError("db down")),
        patch("core.engine.core.db.parse_one", side_effect=RuntimeError("db down")),
        patch("core.engine.intelligence.error_explainer._check_runbook", AsyncMock(return_value=None)),
        patch("core.engine.intelligence.error_explainer._capture_as_runbook", AsyncMock()),
        patch("core.engine.core.llm.get_llm", side_effect=RuntimeError("LLM down")),
    ):
        result = await explain_error(SIMPLE_TB)

    assert isinstance(result, ErrorContext)
    assert result.error_type == "ValueError"


@pytest.mark.asyncio
async def test_explain_error_fallback_explanation_on_llm_failure():
    from core.engine.intelligence.error_explainer import explain_error

    with (
        patch("core.engine.intelligence.error_explainer._check_runbook", AsyncMock(return_value=None)),
        patch("core.engine.intelligence.error_explainer._capture_as_runbook", AsyncMock()),
        patch("core.engine.core.db.pool", _make_db_pool()),
        patch("core.engine.core.db.parse_rows", return_value=[]),
        patch("core.engine.core.db.parse_one", return_value=None),
        patch("core.engine.core.llm.get_llm", side_effect=RuntimeError("LLM down")),
    ):
        result = await explain_error(SIMPLE_TB)

    assert isinstance(result, ErrorContext)
    assert result.explanation != ""
