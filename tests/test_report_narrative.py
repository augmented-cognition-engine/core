# tests/test_report_narrative.py
"""Tests for NarrativeGenerator — LLM-writes plain-language consulting report sections."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_narrative_generates_executive_summary():
    """generate() returns dict with executive_summary and headline_findings."""
    from core.engine.reports.narrative import NarrativeOutput

    mock_result = NarrativeOutput(
        executive_summary="The codebase shows significant security gaps.",
        headline_findings=["Security coverage is critically low", "Testing is incomplete"],
        risk_summaries={"cap_1": "Authentication is missing from core endpoints."},
        recommendation_intro="We recommend addressing security first.",
    )

    mock_llm = MagicMock()
    mock_llm.complete_structured = AsyncMock(return_value=mock_result)

    with patch("core.engine.reports.narrative.get_llm", return_value=mock_llm):
        from core.engine.reports.narrative import NarrativeGenerator

        gen = NarrativeGenerator()
        assembled = {
            "product_name": "TestApp",
            "client_name": "Acme",
            "health_by_discipline": [{"discipline": "security", "avg_score": 0.1, "gap_count": 3}],
            "top_risks": [
                {
                    "discipline": "security",
                    "capability_slug": "cap_1",
                    "score": 0.1,
                    "gaps": ["no auth"],
                    "severity": "critical",
                }
            ],
            "capabilities": [],
            "initiatives": [],
            "recent_decisions": [],
        }
        result = await gen.generate(assembled)

    assert "executive_summary" in result
    assert len(result["headline_findings"]) >= 1
    assert "cap_1" in result["risk_summaries"]


@pytest.mark.asyncio
async def test_narrative_returns_defaults_on_llm_error():
    """LLM failure returns safe fallback text, does not raise."""
    with patch("core.engine.reports.narrative.get_llm", side_effect=RuntimeError("LLM down")):
        from core.engine.reports.narrative import NarrativeGenerator

        gen = NarrativeGenerator()
        result = await gen.generate(
            {
                "product_name": "X",
                "top_risks": [],
                "health_by_discipline": [],
                "capabilities": [],
                "initiatives": [],
                "recent_decisions": [],
                "client_name": "",
            }
        )

    assert "executive_summary" in result
    assert isinstance(result["executive_summary"], str)
    assert len(result["executive_summary"]) > 0
