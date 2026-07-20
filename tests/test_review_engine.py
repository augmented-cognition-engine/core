"""Tests for multi-pass review engine."""

from unittest.mock import AsyncMock, patch

import pytest

from core.engine.github.models import DiffHunk, FileDiff, PRInfo
from core.engine.review.engine import ReviewEngine
from core.engine.review.models import ReviewFinding, ReviewPass


def _make_pr():
    return PRInfo(
        number=42,
        title="Add auth",
        body="JWT auth middleware",
        author="alice",
        base_branch="main",
        head_branch="feature/auth",
        repo_owner="acme",
        repo_name="app",
    )


def _make_files():
    return [
        FileDiff(
            path="core/engine/core/auth.py",
            status="modified",
            hunks=[
                DiffHunk(
                    old_start=10,
                    old_count=6,
                    new_start=10,
                    new_count=8,
                    lines=[
                        " def verify(token):",
                        "+    if not token:",
                        "+        raise ValueError('empty')",
                    ],
                )
            ],
            additions=2,
            deletions=0,
        )
    ]


@pytest.mark.asyncio
async def test_review_selects_relevant_disciplines():
    engine = ReviewEngine(product_id="product:default")
    disciplines = engine.select_disciplines(_make_files())
    assert "security" in disciplines
    assert len(disciplines) >= 2
    assert len(disciplines) <= 5


@pytest.mark.asyncio
async def test_review_runs_parallel_passes():
    engine = ReviewEngine(product_id="product:default")
    mock_pass = ReviewPass(
        discipline="security",
        findings=[
            ReviewFinding(
                file="auth.py",
                line=12,
                message="Missing rate limiting",
                severity="high",
                discipline="security",
            )
        ],
        pass_summary="Found 1 security issue",
    )
    with patch.object(engine, "_run_single_pass", new_callable=AsyncMock, return_value=mock_pass):
        passes = await engine.run_passes(_make_pr(), _make_files(), disciplines=["security", "testing"])
    assert len(passes) == 2


@pytest.mark.asyncio
async def test_review_formats_diff_context():
    engine = ReviewEngine(product_id="product:default")
    context = engine.format_diff_context(_make_files())
    assert "core/engine/core/auth.py" in context
    assert "raise ValueError" in context


@pytest.mark.asyncio
async def test_review_empty_diff_returns_no_passes():
    engine = ReviewEngine(product_id="product:default")
    passes = await engine.run_passes(_make_pr(), [], disciplines=["security"])
    assert len(passes) == 0


@pytest.mark.asyncio
async def test_security_pass_includes_taint_context():
    """Security pass should include taint analysis when source/sink patterns found."""
    engine = ReviewEngine(product_id="product:default")

    # Create a file with taint source and sink
    files = [
        FileDiff(
            path="app.py",
            status="modified",
            hunks=[
                DiffHunk(
                    old_start=1,
                    old_count=5,
                    new_start=1,
                    new_count=7,
                    lines=[
                        "+from flask import request",
                        "+import subprocess",
                        "+def handle():",
                        "+    cmd = request.args.get('cmd')",
                        "+    subprocess.run(cmd, shell=True)",
                    ],
                )
            ],
            additions=5,
            deletions=0,
        )
    ]

    # Mock LLM and check that taint context appears in the prompt
    with (
        patch("core.engine.review.engine.llm") as mock_llm,
        patch(
            "core.engine.orchestrator.loader.load_intelligence",
            new_callable=AsyncMock,
            return_value={"insights": []},
        ),
    ):
        mock_llm.complete = AsyncMock(return_value='{"findings": [], "summary": "clean"}')
        passes = await engine.run_passes(
            PRInfo(number=1, title="test", author="a", base_branch="main", head_branch="feat"),
            files,
            disciplines=["security"],
        )

    # Verify LLM was called with taint context in the prompt
    assert mock_llm.complete.called, "LLM should have been called"
    call_args = mock_llm.complete.call_args
    prompt = call_args[1].get("prompt", "") if call_args[1] else ""
    if not prompt and call_args[0]:
        prompt = call_args[0][0]
    assert "taint" in prompt.lower() or "data flow" in prompt.lower(), (
        f"Expected taint/data flow context in security prompt, got: {prompt[:300]}"
    )
