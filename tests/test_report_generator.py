# tests/test_report_generator.py
"""Tests for PdfRenderer and ReportGenerator — HTML→PDF pipeline."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_generator_returns_bytes():
    """generate() returns non-empty bytes (PDF content)."""
    mock_assembled = {
        "product_name": "TestApp",
        "report_type": "audit",
        "client_name": "Acme",
        "consultant_name": "Ed",
        "generated_at": "April 11, 2026",
        "health_by_discipline": [{"discipline": "security", "avg_score": 0.3, "gap_count": 2}],
        "top_risks": [],
        "capabilities": [],
        "recent_decisions": [],
        "initiatives": [],
        "score_deltas": [],
    }
    mock_narrative = {
        "executive_summary": "Test summary.",
        "headline_findings": ["Finding 1"],
        "risk_summaries": {},
        "recommendation_intro": "Focus here.",
    }
    fake_pdf = b"%PDF-1.4 fake"

    with (
        patch("core.engine.reports.generator.DataAssembler") as MockAssembler,
        patch("core.engine.reports.generator.NarrativeGenerator") as MockNarrative,
        patch("core.engine.reports.generator.PdfRenderer") as MockRenderer,
    ):
        MockAssembler.return_value.assemble = AsyncMock(return_value=mock_assembled)
        MockNarrative.return_value.generate = AsyncMock(return_value=mock_narrative)
        MockRenderer.return_value.render = AsyncMock(return_value=fake_pdf)

        from core.engine.reports.generator import ReportGenerator

        gen = ReportGenerator(pool=MagicMock())
        result = await gen.generate("product:test", report_type="audit", client_name="Acme")

    assert isinstance(result, bytes)
    assert len(result) > 0
    # Confirm diagram section is present in the rendered HTML (sentinel: not silently dropped)
    rendered_html = MockRenderer.return_value.render.call_args[0][0]
    assert "Risk Heat Map" in rendered_html


@pytest.mark.asyncio
async def test_renderer_renders_html_template():
    """PdfRenderer.render() invokes Patchright to produce PDF bytes."""
    fake_pdf = b"%PDF-1.4"

    from core.engine.reports.renderer import PdfRenderer

    renderer = PdfRenderer()

    mock_page = AsyncMock()
    mock_page.pdf = AsyncMock(return_value=fake_pdf)
    mock_browser = AsyncMock()
    mock_browser.new_page = AsyncMock(return_value=mock_page)
    mock_chromium = AsyncMock()
    mock_chromium.launch = AsyncMock(return_value=mock_browser)
    mock_playwright = AsyncMock()
    mock_playwright.chromium = mock_chromium
    mock_pw_ctx = AsyncMock()
    mock_pw_ctx.__aenter__ = AsyncMock(return_value=mock_playwright)
    mock_pw_ctx.__aexit__ = AsyncMock(return_value=None)

    with patch("core.engine.reports.renderer.async_playwright", return_value=mock_pw_ctx):
        result = await renderer.render("<html><body>test</body></html>")

    assert result == fake_pdf
    mock_page.set_content.assert_called_once()
    mock_page.pdf.assert_called_once()
    mock_page.wait_for_selector.assert_called_once_with(".mermaid svg", timeout=8000)


@pytest.mark.asyncio
async def test_generator_uses_snapshot_template_for_snapshot_type():
    """generate() selects snapshot.html when report_type='snapshot'."""
    mock_assembled = {
        "product_name": "App",
        "report_type": "snapshot",
        "client_name": "Corp",
        "consultant_name": "",
        "generated_at": "April 11, 2026",
        "health_by_discipline": [],
        "top_risks": [],
        "capabilities": [],
        "recent_decisions": [],
        "initiatives": [],
        "score_deltas": [{"discipline": "security", "prev_score": 0.2, "curr_score": 0.5, "delta": 0.3}],
    }
    mock_narrative = {
        "executive_summary": "Good progress.",
        "headline_findings": [],
        "risk_summaries": {},
        "recommendation_intro": "",
    }
    fake_pdf = b"%PDF-snapshot"

    with (
        patch("core.engine.reports.generator.DataAssembler") as MockAssembler,
        patch("core.engine.reports.generator.NarrativeGenerator") as MockNarrative,
        patch("core.engine.reports.generator.PdfRenderer") as MockRenderer,
    ):
        MockAssembler.return_value.assemble = AsyncMock(return_value=mock_assembled)
        MockNarrative.return_value.generate = AsyncMock(return_value=mock_narrative)
        MockRenderer.return_value.render = AsyncMock(return_value=fake_pdf)

        from core.engine.reports.generator import ReportGenerator

        gen = ReportGenerator(pool=MagicMock())
        result = await gen.generate("product:test", report_type="snapshot", client_name="Corp")

    assert result == fake_pdf
    # Verify HTML passed to renderer contains snapshot content
    rendered_html = MockRenderer.return_value.render.call_args[0][0]
    assert "Progress Snapshot" in rendered_html
