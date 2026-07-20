# tests/test_question_engine.py
"""Tests for QuestionEngine and question_generator overnight engine.

TDD: tests written before implementation.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_inward_questions_from_unmapped_files():
    """Mock DB returning orphaned files → generates inward questions."""
    from core.engine.product.question_engine import QuestionEngine

    orphaned_files = [
        {"path": "src/payments.py", "change_frequency": 12},
        {"path": "src/billing.py", "change_frequency": 8},
    ]

    mock_pool = MagicMock()
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[[*orphaned_files]])
    mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
    mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

    qe = QuestionEngine(mock_pool)
    questions = await qe._inward_questions("product:default")

    assert len(questions) == 2
    assert all(q["category"] == "inward" for q in questions)
    assert all(q["source"] == "question_engine" for q in questions)
    assert "payments.py" in questions[0]["question"]
    assert "12" in questions[0]["question"]
    assert questions[0]["priority"] == "medium"


@pytest.mark.asyncio
async def test_downward_questions_from_low_scores():
    """Mock DB returning low quality scores → generates downward questions."""
    from core.engine.product.question_engine import QuestionEngine

    low_quality = [
        {
            "capability": "capability:cap1",
            "dimension": "security",
            "score": 0.1,
            "gaps": ["No rate limiting", "Missing MFA"],
        },
        {
            "capability": "capability:cap2",
            "dimension": "testing",
            "score": 0.35,
            "gaps": [],
        },
    ]

    mock_pool = MagicMock()
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[[*low_quality]])
    mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
    mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

    qe = QuestionEngine(mock_pool)
    questions = await qe._downward_questions("product:default")

    assert len(questions) == 2
    assert all(q["category"] == "downward" for q in questions)
    assert all(q["source"] == "question_engine" for q in questions)
    # score < 0.2 → high priority
    assert questions[0]["priority"] == "high"
    # score >= 0.2 → medium priority
    assert questions[1]["priority"] == "medium"
    # first gap used when available
    assert "No rate limiting" in questions[0]["question"]
    # Sentinel: the query must include capability_quality — not a missing/empty SQL string
    call_args = mock_db.query.call_args
    assert call_args is not None, "db.query was never called"
    sql_arg = call_args.args[0] if call_args.args else ""
    assert "capability_quality" in sql_arg, f"Expected capability_quality in SQL, got: {sql_arg!r}"


@pytest.mark.asyncio
async def test_temporal_questions_from_stale_decisions():
    """Mock capabilities with old decisions → generates temporal questions."""
    from core.engine.product.question_engine import QuestionEngine

    old_date = (datetime.now() - timedelta(days=120)).isoformat()
    recent_date = (datetime.now() - timedelta(days=30)).isoformat()

    capabilities = [
        {
            "id": "capability:cap1",
            "slug": "auth",
            "intent": {
                "decisions": [
                    {"decision": "Use JWT tokens", "date": old_date},
                    {"decision": "Use Redis sessions", "date": recent_date},
                ]
            },
        },
        {
            "id": "capability:cap2",
            "slug": "payments",
            "intent": {
                "decisions": [
                    {"decision": "Use Stripe", "date": old_date},
                ]
            },
        },
    ]

    mock_pool = MagicMock()
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[[*capabilities]])
    mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
    mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

    qe = QuestionEngine(mock_pool)
    questions = await qe._temporal_questions("product:default")

    # Only old decisions (> 90 days) should generate questions
    assert len(questions) == 2
    assert all(q["category"] == "temporal" for q in questions)
    assert all(q["source"] == "question_engine" for q in questions)
    question_texts = [q["question"] for q in questions]
    assert any("JWT tokens" in t for t in question_texts)
    assert any("Stripe" in t for t in question_texts)
    # recent decision (30 days) should NOT appear
    assert not any("Redis sessions" in t for t in question_texts)


def test_deduplicate_questions():
    """Duplicate questions with different priorities → keeps highest priority."""
    from core.engine.product.question_engine import QuestionEngine

    mock_pool = MagicMock()
    qe = QuestionEngine(mock_pool)

    questions = [
        {"question": "What is X?", "category": "inward", "source": "q", "priority": "medium"},
        {"question": "What is X?", "category": "inward", "source": "q", "priority": "high"},
        {"question": "What is X?", "category": "inward", "source": "q", "priority": "low"},
        {"question": "What is Y?", "category": "downward", "source": "q", "priority": "low"},
        {"question": "What is Z?", "category": "temporal", "source": "q", "priority": "critical"},
    ]

    result = qe._deduplicate_and_prioritize(questions)

    # 3 unique questions
    assert len(result) == 3
    # "What is X?" should keep the "high" priority version
    x_questions = [q for q in result if q["question"] == "What is X?"]
    assert len(x_questions) == 1
    assert x_questions[0]["priority"] == "high"
    # Results are sorted by priority: critical first, then high, low
    assert result[0]["question"] == "What is Z?"  # critical
    assert result[1]["question"] == "What is X?"  # high
    assert result[2]["question"] == "What is Y?"  # low


@pytest.mark.asyncio
async def test_generate_questions_includes_downward_batch():
    """generate_questions must call _downward_questions and include results.

    Regression guard: before the fix, _downward_questions called db.query with
    no SQL string, silently produced 0 results, and the downward batch was always
    empty. This test asserts downward questions flow through to the final result.
    """
    from core.engine.product.question_engine import QuestionEngine

    low_quality = [
        {
            "capability": "capability:cap1",
            "dimension": "security",
            "score": 0.05,
            "gaps": ["No auth"],
        }
    ]

    call_count = 0

    async def fake_query(sql="", params=None):
        nonlocal call_count
        call_count += 1
        if "capability_quality" in (sql or ""):
            return [[*low_quality]]
        return [[]]

    mock_pool = MagicMock()
    mock_db = AsyncMock()
    mock_db.query.side_effect = fake_query
    mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
    mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

    qe = QuestionEngine(mock_pool)
    questions = await qe.generate_questions("product:default")

    downward = [q for q in questions if q["category"] == "downward"]
    assert len(downward) >= 1, "downward questions missing — _downward_questions SQL may be broken"
    assert "No auth" in downward[0]["question"]


def test_question_generator_engine_registers():
    """question_generator should be in engine_registry after import."""
    from core.engine.sentinel.engines.question_generator import run_question_generator  # noqa: F401
    from core.engine.sentinel.registry import engine_registry

    assert "question_generator" in engine_registry
    entry = engine_registry["question_generator"]
    assert entry["cron"] == "15 3 * * *"
    assert callable(entry["fn"])
