# tests/test_pm_review.py
"""Tests for multi-agent parallel review system."""

from unittest.mock import AsyncMock

import pytest


@pytest.fixture
def mock_llm():
    return AsyncMock()


@pytest.mark.asyncio
async def test_review_parallel_launch(mock_llm):
    """5 review calls run concurrently via asyncio.gather."""
    from core.engine.pm.review import WorkItemReviewer

    call_count = 0

    async def mock_complete_json(prompt, **kwargs):
        nonlocal call_count
        call_count += 1
        return {"issues": [], "summary": "No issues found"}

    mock_llm.complete_json = mock_complete_json

    reviewer = WorkItemReviewer(llm=mock_llm)
    result = await reviewer.review_work_item(
        work_item={
            "title": "Create schema",
            "description": "Build token schema",
            "domain_path": "architecture",
        },
        initiative={"title": "Multi-brand tokens", "success_criteria": ["Schema complete"]},
        output="def create_schema(): pass",
        product_id="product:test",
    )

    assert call_count == 5  # 5 parallel dimensions
    assert result["passed"] is True
    assert len(result["stages"]) == 5


@pytest.mark.asyncio
async def test_review_confidence_filter(mock_llm):
    """Issues below confidence threshold are filtered out."""
    from core.engine.pm.review import WorkItemReviewer

    async def mock_complete_json(prompt, **kwargs):
        if "spec compliance" in prompt.lower():
            return {
                "issues": [
                    {"description": "Missing validation", "severity": "major", "confidence": 90},
                    {"description": "Minor style issue", "severity": "minor", "confidence": 50},
                ],
                "summary": "Some issues",
            }
        return {"issues": [], "summary": "OK"}

    mock_llm.complete_json = mock_complete_json

    reviewer = WorkItemReviewer(llm=mock_llm, confidence_threshold=80)
    result = await reviewer.review_work_item(
        work_item={"title": "Test", "description": "Test", "domain_path": "tech"},
        initiative={"title": "Init", "success_criteria": []},
        output="code here",
        product_id="product:test",
    )

    # Only the 90-confidence issue should surface
    all_issues = result["all_issues"]
    assert len(all_issues) == 1
    assert all_issues[0]["confidence"] == 90


@pytest.mark.asyncio
async def test_review_critical_blocks(mock_llm):
    """Critical issues block work item completion."""
    from core.engine.pm.review import WorkItemReviewer

    async def mock_complete_json(prompt, **kwargs):
        if "error handling" in prompt.lower():
            return {
                "issues": [
                    {"description": "Unhandled exception in main path", "severity": "critical", "confidence": 95},
                ],
                "summary": "Critical issue found",
            }
        return {"issues": [], "summary": "OK"}

    mock_llm.complete_json = mock_complete_json

    reviewer = WorkItemReviewer(llm=mock_llm)
    result = await reviewer.review_work_item(
        work_item={"title": "Test", "description": "Test", "domain_path": "tech"},
        initiative={"title": "Init", "success_criteria": []},
        output="code with bugs",
        product_id="product:test",
    )

    assert result["passed"] is False
    assert result["critical_count"] == 1


@pytest.mark.asyncio
async def test_review_major_flags(mock_llm):
    """Major issues flag but do not block."""
    from core.engine.pm.review import WorkItemReviewer

    async def mock_complete_json(prompt, **kwargs):
        if "test coverage" in prompt.lower():
            return {
                "issues": [
                    {"description": "Missing edge case test", "severity": "major", "confidence": 85},
                ],
                "summary": "Coverage gap",
            }
        return {"issues": [], "summary": "OK"}

    mock_llm.complete_json = mock_complete_json

    reviewer = WorkItemReviewer(llm=mock_llm)
    result = await reviewer.review_work_item(
        work_item={"title": "Test", "description": "Test", "domain_path": "tech"},
        initiative={"title": "Init", "success_criteria": []},
        output="code",
        product_id="product:test",
    )

    assert result["passed"] is True  # major doesn't block
    assert result["needs_attention"] is True
    assert result["major_count"] == 1


@pytest.mark.asyncio
async def test_review_all_pass(mock_llm):
    """All dimensions pass with no issues."""
    from core.engine.pm.review import WorkItemReviewer

    async def mock_complete_json(prompt, **kwargs):
        return {"issues": [], "summary": "All good"}

    mock_llm.complete_json = mock_complete_json

    reviewer = WorkItemReviewer(llm=mock_llm)
    result = await reviewer.review_work_item(
        work_item={"title": "Test", "description": "Test", "domain_path": "tech"},
        initiative={"title": "Init", "success_criteria": []},
        output="clean code",
        product_id="product:test",
    )

    assert result["passed"] is True
    assert result["needs_attention"] is False
    assert result["critical_count"] == 0
    assert result["major_count"] == 0


@pytest.mark.asyncio
async def test_review_custom_threshold(mock_llm):
    """Custom confidence threshold filters differently."""
    from core.engine.pm.review import WorkItemReviewer

    async def mock_complete_json(prompt, **kwargs):
        return {
            "issues": [
                {"description": "Medium confidence issue", "severity": "major", "confidence": 70},
            ],
            "summary": "Some issues",
        }

    mock_llm.complete_json = mock_complete_json

    # With default 80 threshold — filtered out
    reviewer80 = WorkItemReviewer(llm=mock_llm, confidence_threshold=80)
    result80 = await reviewer80.review_work_item(
        work_item={"title": "T", "description": "T", "domain_path": "t"},
        initiative={"title": "I", "success_criteria": []},
        output="code",
        product_id="product:test",
    )
    assert len(result80["all_issues"]) == 0

    # With 60 threshold — included
    reviewer60 = WorkItemReviewer(llm=mock_llm, confidence_threshold=60)
    result60 = await reviewer60.review_work_item(
        work_item={"title": "T", "description": "T", "domain_path": "t"},
        initiative={"title": "I", "success_criteria": []},
        output="code",
        product_id="product:test",
    )
    assert len(result60["all_issues"]) == 5  # 5 dimensions × 1 issue each
