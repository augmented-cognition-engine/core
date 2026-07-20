"""Tests for the lint/test reflection loop."""

from unittest.mock import patch

import pytest

from core.engine.runtime.reflection import ReflectionLoop


def test_initial_state():
    loop = ReflectionLoop()
    assert loop.reflection_count == 0
    assert loop.can_reflect()


def test_max_reflections():
    loop = ReflectionLoop(lint_cmd="false")
    assert loop.can_reflect()
    loop._reflection_count = 3
    assert not loop.can_reflect()


def test_reset():
    loop = ReflectionLoop()
    loop._reflection_count = 2
    loop.reset()
    assert loop.reflection_count == 0


@pytest.mark.asyncio
async def test_validate_no_commands():
    loop = ReflectionLoop()
    result = await loop.validate()
    assert result is None  # no commands configured = always clean


@pytest.mark.asyncio
async def test_validate_passing_command():
    loop = ReflectionLoop(lint_cmd="true")
    result = await loop.validate()
    assert result is None


@pytest.mark.asyncio
async def test_validate_failing_command():
    loop = ReflectionLoop(lint_cmd="echo 'error: syntax' && exit 1")
    result = await loop.validate()
    assert result is not None
    assert "error" in result.lower() or "syntax" in result.lower()
    assert loop.reflection_count == 1


# ---------------------------------------------------------------------------
# Discipline-aware validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_unknown_discipline_no_extra_check():
    """Unrecognised disciplines fall through to base lint + test only."""
    loop = ReflectionLoop(lint_cmd="true")
    result = await loop.validate(modified_files=["engine/foo.py"], discipline="documentation")
    assert result is None


@pytest.mark.asyncio
async def test_validate_security_discipline_skips_if_bandit_missing():
    """If bandit is not installed, security check is silently skipped."""
    loop = ReflectionLoop(lint_cmd="true")
    with patch("shutil.which", return_value=None):
        result = await loop.validate(modified_files=["engine/auth.py"], discipline="security")
    assert result is None


@pytest.mark.asyncio
async def test_validate_security_discipline_skips_non_python_files():
    """bandit only runs on .py files — JS/TS edits don't trigger it."""
    loop = ReflectionLoop(lint_cmd="true")
    with patch("shutil.which", return_value="/usr/bin/bandit"):
        result = await loop.validate(modified_files=["frontend/app.tsx"], discipline="security")
    assert result is None


@pytest.mark.asyncio
async def test_validate_security_discipline_runs_bandit_on_py_files():
    """When bandit is available, runs it on modified Python files."""
    loop = ReflectionLoop(lint_cmd="true")

    bandit_ran_on = []

    async def mock_run_cmd(cmd: str):
        if "bandit" in cmd:
            bandit_ran_on.append(cmd)
        return None  # clean result

    loop._run_cmd = mock_run_cmd

    with patch("shutil.which", return_value="/usr/bin/bandit"):
        result = await loop.validate(modified_files=["engine/auth.py", "engine/api.py"], discipline="security")

    assert result is None
    assert len(bandit_ran_on) == 1
    assert "engine/auth.py" in bandit_ran_on[0]
    assert "engine/api.py" in bandit_ran_on[0]


@pytest.mark.asyncio
async def test_validate_security_bandit_findings_surfaced():
    """bandit findings are included in the returned error string."""
    loop = ReflectionLoop(lint_cmd="true")

    async def mock_run_cmd(cmd: str):
        if "bandit" in cmd:
            # Simulate bandit reporting an issue — non-zero exit returned as string
            return "Issue: [B105:hardcoded_password_string]\nExit code: 1"
        return None

    loop._run_cmd = mock_run_cmd

    with patch("shutil.which", return_value="/usr/bin/bandit"):
        result = await loop.validate(modified_files=["engine/auth.py"], discipline="security")

    assert result is not None
    assert "Security issues" in result
    assert "bandit" in result.lower() or "B105" in result


@pytest.mark.asyncio
async def test_validate_discipline_none_no_extra_checks():
    """No discipline = no extra checks, only base lint + test."""
    loop = ReflectionLoop(lint_cmd="true")
    result = await loop.validate(modified_files=["engine/foo.py"], discipline=None)
    assert result is None


@pytest.mark.asyncio
async def test_validate_no_files_with_discipline():
    """Discipline check requires modified_files — None means skip extra checks."""
    loop = ReflectionLoop(lint_cmd="true")
    with patch("shutil.which", return_value="/usr/bin/bandit"):
        result = await loop.validate(modified_files=None, discipline="security")
    assert result is None


def test_runtime_stores_discipline_after_classify():
    """Runtime._current_discipline is populated from intelligence classification."""
    from core.engine.runtime.model_adapter import MockAdapter
    from core.engine.runtime.runtime import Runtime

    rt = Runtime(adapter=MockAdapter(responses=[]), enable_intelligence=False)
    # Intelligence disabled — discipline stays None
    assert rt._current_discipline is None
