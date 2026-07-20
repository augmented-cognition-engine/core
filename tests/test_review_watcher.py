"""Tests for automated review watcher."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.engine.review.watcher import check_and_review


@pytest.mark.asyncio
async def test_skip_main_branch():
    """Should not review main against itself."""
    with patch("core.engine.review.watcher.subprocess") as mock_sub:
        mock_sub.run.return_value = MagicMock(stdout="main\n", returncode=0)
        result = await check_and_review(repo_path="/tmp")
    assert result is None


@pytest.mark.asyncio
async def test_skip_already_reviewed():
    """Should skip if HEAD SHA was already reviewed."""
    with (
        patch("core.engine.review.watcher.subprocess") as mock_sub,
        patch("core.engine.review.watcher.pool") as mock_pool,
    ):
        mock_sub.run.side_effect = [
            MagicMock(stdout="feature\n", returncode=0),  # branch
            MagicMock(stdout="abc123\n", returncode=0),  # SHA
        ]
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[[{"id": "pr_review:existing"}]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await check_and_review(repo_path="/tmp")
    assert result is None


@pytest.mark.asyncio
async def test_runs_review_on_feature_branch():
    """Should run review when on feature branch with changes."""
    with (
        patch("core.engine.review.watcher.subprocess") as mock_sub,
        patch("core.engine.review.watcher.pool") as mock_pool,
        patch("core.engine.review.watcher.LocalGitProvider") as mock_provider_cls,
        patch("core.engine.review.watcher.ReviewEngine") as mock_engine_cls,
        patch("core.engine.review.watcher.Judge") as mock_judge_cls,
        patch("core.engine.review.watcher.PRImpactAnalyzer") as mock_impact_cls,
    ):
        # Git commands
        mock_sub.run.side_effect = [
            MagicMock(stdout="feature\n", returncode=0),
            MagicMock(stdout="abc123\n", returncode=0),
        ]

        # DB: no existing review, then persist succeeds
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[[]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        # Provider returns files
        from core.engine.github.models import DiffHunk, FileDiff, PRInfo

        mock_provider = AsyncMock()
        mock_provider.get_diff.return_value = (
            PRInfo(
                number=0,
                title="feature \u2192 main",
                author="test",
                base_branch="main",
                head_branch="feature",
            ),
            [
                FileDiff(
                    path="test.py",
                    status="modified",
                    additions=1,
                    hunks=[
                        DiffHunk(
                            old_start=1,
                            old_count=1,
                            new_start=1,
                            new_count=2,
                            lines=["+new line"],
                        )
                    ],
                )
            ],
        )
        mock_provider_cls.return_value = mock_provider

        # Engine returns passes
        from core.engine.review.models import ReviewPass, ReviewSynthesis

        mock_engine = AsyncMock()
        mock_engine.run_passes.return_value = [ReviewPass(discipline="security", findings=[], pass_summary="clean")]
        mock_engine_cls.return_value = mock_engine

        # Judge returns synthesis
        mock_judge = AsyncMock()
        mock_judge.synthesize.return_value = ReviewSynthesis(
            findings=[],
            summary="Clean",
            passes_run=1,
            findings_before_judge=0,
            findings_after_judge=0,
            pass_quality_gate=True,
        )
        mock_judge_cls.return_value = mock_judge

        # Impact analyzer
        mock_impact = AsyncMock()
        mock_impact.full_impact.return_value = {}
        mock_impact_cls.return_value = mock_impact

        result = await check_and_review(repo_path="/tmp")

    assert result is not None
    assert result["branch"] == "feature"
    assert result["pass_quality_gate"] is True
    assert result["findings_count"] == 0


@pytest.mark.asyncio
async def test_no_files_returns_none():
    """Should return None when diff has no changed files."""
    with (
        patch("core.engine.review.watcher.subprocess") as mock_sub,
        patch("core.engine.review.watcher.pool") as mock_pool,
        patch("core.engine.review.watcher.LocalGitProvider") as mock_provider_cls,
    ):
        mock_sub.run.side_effect = [
            MagicMock(stdout="feature\n", returncode=0),
            MagicMock(stdout="deadbeef\n", returncode=0),
        ]

        # DB: no existing review
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[[]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        from core.engine.github.models import PRInfo

        mock_provider = AsyncMock()
        mock_provider.get_diff.return_value = (
            PRInfo(number=0, title="feature \u2192 main", author="test", base_branch="main", head_branch="feature"),
            [],  # no files
        )
        mock_provider_cls.return_value = mock_provider

        result = await check_and_review(repo_path="/tmp")

    assert result is None


@pytest.mark.asyncio
async def test_force_skips_sha_check():
    """With force=True, should skip the duplicate-SHA guard."""
    with (
        patch("core.engine.review.watcher.subprocess") as mock_sub,
        patch("core.engine.review.watcher.pool") as mock_pool,
        patch("core.engine.review.watcher.LocalGitProvider") as mock_provider_cls,
        patch("core.engine.review.watcher.ReviewEngine") as mock_engine_cls,
        patch("core.engine.review.watcher.Judge") as mock_judge_cls,
        patch("core.engine.review.watcher.PRImpactAnalyzer") as mock_impact_cls,
    ):
        mock_sub.run.side_effect = [
            MagicMock(stdout="feature\n", returncode=0),
            MagicMock(stdout="abc123\n", returncode=0),
        ]

        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[[]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        from core.engine.github.models import DiffHunk, FileDiff, PRInfo

        mock_provider = AsyncMock()
        mock_provider.get_diff.return_value = (
            PRInfo(number=0, title="feature \u2192 main", author="test", base_branch="main", head_branch="feature"),
            [
                FileDiff(
                    path="src/main.py",
                    status="modified",
                    additions=2,
                    hunks=[DiffHunk(old_start=1, old_count=1, new_start=1, new_count=2, lines=["+x = 1"])],
                )
            ],
        )
        mock_provider_cls.return_value = mock_provider

        from core.engine.review.models import ReviewPass, ReviewSynthesis

        mock_engine = AsyncMock()
        mock_engine.run_passes.return_value = [ReviewPass(discipline="architecture", findings=[])]
        mock_engine_cls.return_value = mock_engine

        mock_judge = AsyncMock()
        mock_judge.synthesize.return_value = ReviewSynthesis(
            findings=[],
            summary="OK",
            passes_run=1,
            findings_before_judge=0,
            findings_after_judge=0,
            pass_quality_gate=True,
        )
        mock_judge_cls.return_value = mock_judge

        mock_impact = AsyncMock()
        mock_impact.full_impact.return_value = {}
        mock_impact_cls.return_value = mock_impact

        result = await check_and_review(repo_path="/tmp", force=True)

    # Should have run the review (not returned None) without querying DB for SHA
    assert result is not None
    assert result["branch"] == "feature"
