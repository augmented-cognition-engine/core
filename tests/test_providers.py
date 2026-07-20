"""Tests for git provider adapters."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.engine.review.providers import (
    GitHubProvider,
    GitLabProvider,
    LocalGitProvider,
    _get_current_branch,
    _run_git,
    create_provider,
)

# --- Factory tests ---


def test_create_local_provider():
    p = create_provider("local")
    assert isinstance(p, LocalGitProvider)


def test_create_local_with_path():
    p = create_provider("local:/tmp/repo")
    assert isinstance(p, LocalGitProvider)
    # LocalGitProvider resolves the path (Path.resolve), which follows symlinks —
    # /tmp -> /private/tmp on macOS — so compare against the resolved form.
    assert p.repo_path == Path("/tmp/repo").resolve()


def test_create_github_provider_from_url():
    p = create_provider("https://github.com/acme/app/pull/42")
    assert isinstance(p, GitHubProvider)
    assert p.owner == "acme"
    assert p.repo == "app"
    assert p.pr_number == 42


def test_create_github_provider_from_shorthand():
    p = create_provider("github:acme/app#99")
    assert isinstance(p, GitHubProvider)
    assert p.pr_number == 99


def test_create_gitlab_provider():
    p = create_provider("gitlab:group/project!15")
    assert isinstance(p, GitLabProvider)
    assert p.project_id == "group/project"
    assert p.mr_iid == 15


def test_create_gitlab_self_hosted():
    p = create_provider("gitlab:https://git.example.com/team/repo!7")
    assert isinstance(p, GitLabProvider)
    assert p.base_url == "https://git.example.com"
    assert p.mr_iid == 7


def test_create_unknown_raises():
    with pytest.raises(ValueError, match="Unknown source"):
        create_provider("bitbucket:foo/bar#1")


# --- Local git tests ---


@pytest.mark.asyncio
async def test_local_provider_get_diff():
    provider = LocalGitProvider(repo_path="/tmp", base_branch="main", head_branch="feature")

    mock_diff = "diff --git a/test.py b/test.py\nindex abc..def 100644\n--- a/test.py\n+++ b/test.py\n@@ -1,1 +1,2 @@\n old\n+new\n"

    with patch("core.engine.review.providers._run_git") as mock_git:
        mock_git.side_effect = lambda repo, *args: {
            ("diff", "main...feature"): mock_diff,
            ("config", "user.name"): "Alice\n",
            ("rev-parse", "--abbrev-ref", "HEAD"): "feature\n",
        }.get(args, "")
        pr, files = await provider.get_diff()

    assert pr.head_branch == "feature"
    assert pr.base_branch == "main"
    assert len(files) == 1
    assert files[0].path == "test.py"


@pytest.mark.asyncio
async def test_local_provider_post_review_is_noop():
    provider = LocalGitProvider()
    await provider.post_review(MagicMock())  # should not raise


@pytest.mark.asyncio
async def test_local_provider_post_status_is_noop():
    provider = LocalGitProvider()
    await provider.post_status("success", "all good")  # should not raise


# --- Helpers ---


def test_run_git_returns_stdout():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="main\n", stderr="")
        result = _run_git(Path("/tmp"), "rev-parse", "--abbrev-ref", "HEAD")
    assert result == "main\n"


def test_run_git_returns_empty_on_error():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
        result = _run_git(Path("/tmp"), "bad-command")
    assert result == ""


def test_get_current_branch():
    with patch("core.engine.review.providers._run_git", return_value="feature-branch\n"):
        branch = _get_current_branch(Path("/tmp"))
    assert branch == "feature-branch"
