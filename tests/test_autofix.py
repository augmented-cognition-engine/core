"""Tests for auto-fix PR generation."""

import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.engine.review.autofix import AutofixAgent
from core.engine.review.models import ReviewFinding, ReviewSynthesis


def _make_synthesis(with_fixes=True):
    findings = [
        ReviewFinding(
            file="auth.py",
            line=15,
            message="Hardcoded secret",
            severity="critical",
            discipline="security",
            suggested_fix="Use environment variable" if with_fixes else "",
        ),
        ReviewFinding(
            file="auth.py",
            line=30,
            message="Missing validation",
            severity="high",
            discipline="security",
            suggested_fix="Add input validation" if with_fixes else "",
        ),
        ReviewFinding(
            file="api.py",
            line=5,
            message="Style issue",
            severity="low",
            discipline="architecture",
        ),
    ]
    return ReviewSynthesis(
        findings=findings,
        summary="test",
        passes_run=2,
        findings_before_judge=3,
        findings_after_judge=3,
    )


def test_should_autofix_with_fixable_findings():
    agent = AutofixAgent(gh=MagicMock())
    assert agent.should_autofix(_make_synthesis(with_fixes=True)) is True


def test_should_not_autofix_without_fixes():
    agent = AutofixAgent(gh=MagicMock())
    assert agent.should_autofix(_make_synthesis(with_fixes=False)) is False


def test_get_fixable_findings():
    agent = AutofixAgent(gh=MagicMock())
    fixable = agent.get_fixable_findings(_make_synthesis())
    assert len(fixable) == 2  # only critical + high with suggested_fix
    assert all(f.severity in ("critical", "high") for f in fixable)


@pytest.mark.asyncio
async def test_generate_fix():
    agent = AutofixAgent(gh=MagicMock())
    finding = ReviewFinding(
        file="auth.py",
        line=15,
        message="Hardcoded secret",
        severity="critical",
        discipline="security",
        suggested_fix="Use os.environ",
    )
    with patch("core.engine.review.autofix.llm") as mock_llm:
        mock_llm.complete = AsyncMock(return_value='import os\n\nsecret = os.environ["SECRET_KEY"]')
        fixed = await agent.generate_fix(finding, 'secret = "hardcoded"')

    assert fixed is not None
    assert "os.environ" in fixed


@pytest.mark.asyncio
async def test_generate_fix_strips_code_fences():
    agent = AutofixAgent(gh=MagicMock())
    finding = ReviewFinding(file="a.py", line=1, message="test", severity="high", suggested_fix="fix")
    with patch("core.engine.review.autofix.llm") as mock_llm:
        mock_llm.complete = AsyncMock(return_value="```python\nfixed = True\n```")
        fixed = await agent.generate_fix(finding, "broken = True")
    assert fixed == "fixed = True"


@pytest.mark.asyncio
async def test_run_no_fixable():
    agent = AutofixAgent(gh=MagicMock())
    result = await agent.run("owner", "repo", 1, "main", _make_synthesis(with_fixes=False))
    assert result is None


@pytest.mark.asyncio
async def test_apply_local_fixes():
    """Local autofix applies fixes to files and commits."""
    import tempfile
    from pathlib import Path

    agent = AutofixAgent(gh=MagicMock())

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a fake git repo
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmpdir, capture_output=True)

        # Create a file with an issue
        test_file = Path(tmpdir) / "auth.py"
        test_file.write_text('secret = "hardcoded"\n')
        subprocess.run(["git", "add", "."], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=tmpdir, capture_output=True)

        synthesis = _make_synthesis(with_fixes=True)

        fixed_content = 'import os\nsecret = os.environ["SECRET"]\n'
        with patch.object(agent, "generate_fix", new_callable=AsyncMock, return_value=fixed_content):
            result = await agent.apply_local_fixes(tmpdir, synthesis)

        assert result["files_fixed"] == 1
        assert "auth.py" in result["files"]
        assert "os.environ" in test_file.read_text()


@pytest.mark.asyncio
async def test_apply_local_fixes_no_fixable():
    """Returns zero when there are no fixable findings."""
    agent = AutofixAgent(gh=MagicMock())
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        result = await agent.apply_local_fixes(tmpdir, _make_synthesis(with_fixes=False))
    assert result["files_fixed"] == 0
    assert result["files"] == []


@pytest.mark.asyncio
async def test_apply_local_fixes_missing_file():
    """Skips files that don't exist in the repo."""
    import tempfile

    agent = AutofixAgent(gh=MagicMock())

    with tempfile.TemporaryDirectory() as tmpdir:
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "commit", "--allow-empty", "-m", "initial"], cwd=tmpdir, capture_output=True)

        # synthesis references auth.py which doesn't exist in tmpdir
        synthesis = _make_synthesis(with_fixes=True)
        fixed_content = 'import os\nsecret = os.environ["SECRET"]\n'
        with patch.object(agent, "generate_fix", new_callable=AsyncMock, return_value=fixed_content):
            result = await agent.apply_local_fixes(tmpdir, synthesis)

        assert result["files_fixed"] == 0
