# tests/test_mcp_pr_review.py
"""Tests for ace_pr_review MCP tool."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_ace_pr_review_tool_exists():
    from core.engine.github.models import FileDiff, PRInfo
    from core.engine.mcp.tools import ace_pr_review

    mock_pr = PRInfo(number=42, title="Test PR", author="alice", base_branch="main", head_branch="feature")
    mock_files = [FileDiff(path="auth.py", additions=5, deletions=2)]

    mock_provider = MagicMock()
    mock_provider.get_diff = AsyncMock(return_value=(mock_pr, mock_files))
    mock_provider.post_review = AsyncMock()

    mock_synthesis = MagicMock()
    mock_synthesis.findings = []
    mock_synthesis.summary = "1 finding"
    mock_synthesis.discipline_scores = {"security": 0.7}
    mock_synthesis.pass_quality_gate = True
    mock_synthesis.gate_failures = []
    mock_synthesis.findings = []

    with (
        patch("core.engine.review.providers.create_provider", return_value=mock_provider),
        patch("core.engine.review.engine.ReviewEngine") as mock_engine_cls,
        patch("core.engine.review.judge.Judge") as mock_judge_cls,
        patch("core.engine.review.impact.PRImpactAnalyzer") as mock_analyzer_cls,
    ):
        mock_engine = MagicMock()
        mock_engine.run_passes = AsyncMock(return_value=[])
        mock_engine_cls.return_value = mock_engine

        mock_judge = MagicMock()
        mock_judge.synthesize = AsyncMock(return_value=mock_synthesis)
        mock_judge_cls.return_value = mock_judge

        mock_analyzer = MagicMock()
        mock_analyzer.full_impact = AsyncMock(return_value={})
        mock_analyzer_cls.return_value = mock_analyzer

        result = await ace_pr_review(pr_url="https://github.com/acme/app/pull/42")

    assert result["findings_count"] == 0
    assert result["pass_quality_gate"] is True
    assert "autofix" in result  # autofix key always present


@pytest.mark.asyncio
async def test_ace_pr_review_autofix_github():
    """When provider is GitHubProvider with fixable findings, autofix.run() is called."""
    from core.engine.github.models import FileDiff, PRInfo
    from core.engine.mcp.tools import ace_pr_review
    from core.engine.review.models import ReviewFinding, ReviewSynthesis

    mock_pr = PRInfo(number=10, title="Fix PR", author="bob", base_branch="main", head_branch="fix-branch")
    mock_files = [FileDiff(path="auth.py", additions=3, deletions=1)]

    finding = ReviewFinding(
        file="auth.py",
        line=5,
        message="Hardcoded secret",
        severity="critical",
        discipline="security",
        suggested_fix="Use env var",
    )
    synthesis = ReviewSynthesis(
        findings=[finding],
        summary="critical issue",
        passes_run=1,
        findings_before_judge=1,
        findings_after_judge=1,
    )

    from core.engine.review.providers import GitHubProvider

    mock_provider = MagicMock(spec=GitHubProvider)
    mock_provider.owner = "acme"
    mock_provider.repo = "app"
    mock_provider.get_diff = AsyncMock(return_value=(mock_pr, mock_files))
    mock_provider.post_review = AsyncMock()

    mock_fix_pr = {"number": 99, "html_url": "https://github.com/acme/app/pull/99"}

    with (
        patch("core.engine.review.providers.create_provider", return_value=mock_provider),
        patch("core.engine.review.engine.ReviewEngine") as mock_engine_cls,
        patch("core.engine.review.judge.Judge") as mock_judge_cls,
        patch("core.engine.review.impact.PRImpactAnalyzer") as mock_analyzer_cls,
        patch("core.engine.review.autofix.AutofixAgent") as mock_agent_cls,
    ):
        mock_engine = MagicMock()
        mock_engine.run_passes = AsyncMock(return_value=[])
        mock_engine_cls.return_value = mock_engine

        mock_judge = MagicMock()
        mock_judge.synthesize = AsyncMock(return_value=synthesis)
        mock_judge_cls.return_value = mock_judge

        mock_analyzer = MagicMock()
        mock_analyzer.full_impact = AsyncMock(return_value={})
        mock_analyzer_cls.return_value = mock_analyzer

        mock_agent = MagicMock()
        mock_agent.should_autofix = MagicMock(return_value=True)
        mock_agent.run = AsyncMock(return_value=mock_fix_pr)
        mock_agent_cls.return_value = mock_agent

        result = await ace_pr_review(source="github:acme/app#10")

    assert result["autofix"] is not None
    assert result["autofix"]["type"] == "github_pr"
    assert result["autofix"]["pr_number"] == 99


@pytest.mark.asyncio
async def test_ace_pr_review_invalid_url():
    from core.engine.mcp.tools import ace_pr_review

    result = await ace_pr_review(pr_url="not-a-url")
    assert "error" in result
