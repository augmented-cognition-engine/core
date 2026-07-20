# tests/test_intelligence_distillation_export.py
"""Tests for STaR-trace distillation corpus export — fine-tune-ready JSONL.

STaR traces are successful reasoning patterns captured after VerificationGate.
Exporting them as JSONL gives organizations a dataset they can use to fine-tune
a smaller model (e.g. Haiku) on their captured reasoning — turning ACE's
run-time intelligence into training-time intelligence.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_distillation_export_emits_one_line_per_trace():
    from core.engine.intelligence.distillation_export import export_distillation_jsonl

    traces = [
        {
            "task_description": "refactor auth module",
            "final_output": "extracted middleware...",
            "discipline": "architecture",
            "confidence": 0.92,
        },
        {
            "task_description": "add rate limit",
            "final_output": "token bucket at route layer",
            "discipline": "architecture",
            "confidence": 0.88,
        },
    ]

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[traces])

    jsonl = await export_distillation_jsonl(mock_db, product_id="product:test")
    lines = [line for line in jsonl.splitlines() if line.strip()]
    assert len(lines) == 2


@pytest.mark.asyncio
async def test_distillation_export_each_line_parses_as_training_record():
    from core.engine.intelligence.distillation_export import export_distillation_jsonl

    trace = {
        "task_description": "pick a cache strategy",
        "final_output": "LRU 10k entries",
        "discipline": "performance",
        "confidence": 0.95,
    }

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[[trace]])

    jsonl = await export_distillation_jsonl(mock_db, product_id="product:test")
    line = jsonl.splitlines()[0]
    parsed = json.loads(line)
    # OpenAI-style prompt/completion training format
    assert parsed["prompt"] == "pick a cache strategy"
    assert parsed["completion"] == "LRU 10k entries"
    # Metadata rides along
    assert parsed["metadata"]["discipline"] == "performance"
    assert parsed["metadata"]["confidence"] == pytest.approx(0.95)


@pytest.mark.asyncio
async def test_distillation_export_filters_by_discipline():
    from core.engine.intelligence.distillation_export import export_distillation_jsonl

    captured_params: list[dict] = []

    async def fake_query(sql, params=None):
        captured_params.append(params or {})
        return [[]]

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=fake_query)

    await export_distillation_jsonl(mock_db, product_id="product:test", discipline="security")
    assert captured_params
    assert captured_params[0].get("discipline") == "security"


@pytest.mark.asyncio
async def test_distillation_export_empty_returns_empty_string():
    from core.engine.intelligence.distillation_export import export_distillation_jsonl

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[[]])

    jsonl = await export_distillation_jsonl(mock_db, product_id="product:test")
    assert jsonl == ""


@pytest.mark.asyncio
async def test_distillation_export_failure_returns_empty():
    from core.engine.intelligence.distillation_export import export_distillation_jsonl

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=RuntimeError("db gone"))

    jsonl = await export_distillation_jsonl(mock_db, product_id="product:test")
    assert jsonl == ""


@pytest.mark.asyncio
async def test_distillation_export_min_confidence_filter():
    """Callers can require a minimum confidence to keep the dataset high-quality."""
    from core.engine.intelligence.distillation_export import export_distillation_jsonl

    captured_params: list[dict] = []

    async def fake_query(sql, params=None):
        captured_params.append(params or {})
        return [[]]

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=fake_query)

    await export_distillation_jsonl(mock_db, product_id="product:test", min_confidence=0.8)
    assert captured_params
    assert captured_params[0].get("min_confidence") == pytest.approx(0.8)
