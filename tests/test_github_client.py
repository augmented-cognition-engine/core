"""Tests for engine/github/client.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.engine.github.client import GitHubClient
from core.engine.github.models import PRInfo

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pr_response() -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.headers = {"X-RateLimit-Remaining": "59"}
    resp.json.return_value = {
        "number": 42,
        "title": "Fix bug in parser",
        "body": "This fixes the edge case.",
        "user": {"login": "octocat"},
        "base": {"ref": "main"},
        "head": {"ref": "fix/parser-edge-case", "sha": "abc123def456"},
        "changed_files": 3,
        "additions": 15,
        "deletions": 5,
    }
    return resp


def _make_diff_response() -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.headers = {"X-RateLimit-Remaining": "58"}
    resp.text = "diff --git a/foo.py b/foo.py\n+new line\n-old line\n"
    return resp


def _make_review_response() -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.headers = {"X-RateLimit-Remaining": "57"}
    resp.json.return_value = {"id": 999, "state": "COMMENTED", "body": "Looks good."}
    return resp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_pr_info():
    client = GitHubClient(token="test-token")
    mock_resp = _make_pr_response()

    with patch.object(client, "_request", new=AsyncMock(return_value=mock_resp)):
        pr = await client.fetch_pr("acme", "app", 42)

    assert isinstance(pr, PRInfo)
    assert pr.number == 42
    assert pr.title == "Fix bug in parser"
    assert pr.body == "This fixes the edge case."
    assert pr.author == "octocat"
    assert pr.base_branch == "main"
    assert pr.head_branch == "fix/parser-edge-case"
    assert pr.repo_owner == "acme"
    assert pr.repo_name == "app"
    assert pr.files_changed == 3
    assert pr.additions == 15
    assert pr.deletions == 5
    assert pr.head_sha == "abc123def456"


@pytest.mark.asyncio
async def test_fetch_pr_diff():
    client = GitHubClient(token="test-token")
    mock_resp = _make_diff_response()

    with patch.object(client, "_request", new=AsyncMock(return_value=mock_resp)) as mock_req:
        diff = await client.fetch_diff("acme", "app", 42)

    assert "diff --git" in diff
    assert "+new line" in diff
    # Verify correct accept header was passed
    _, kwargs = mock_req.call_args
    assert kwargs.get("accept") == "application/vnd.github.diff"


@pytest.mark.asyncio
async def test_post_review_comment():
    client = GitHubClient(token="test-token")
    mock_resp = _make_review_response()
    comments = [{"path": "foo.py", "line": 10, "body": "Consider using a dict here."}]

    with patch.object(client, "_request", new=AsyncMock(return_value=mock_resp)) as mock_req:
        result = await client.post_review(
            "acme",
            "app",
            42,
            body="Looks good.",
            comments=comments,
            event="COMMENT",
        )

    assert result["id"] == 999
    assert result["state"] == "COMMENTED"
    # Verify payload passed to _request
    _, kwargs = mock_req.call_args
    payload = kwargs.get("json")
    assert payload["body"] == "Looks good."
    assert payload["event"] == "COMMENT"
    assert payload["comments"] == comments


def test_parse_pr_url():
    owner, repo, number = GitHubClient.parse_pr_url("https://github.com/acme/app/pull/123")
    assert owner == "acme"
    assert repo == "app"
    assert number == 123


def test_parse_pr_url_invalid():
    with pytest.raises(ValueError, match="Invalid GitHub PR URL"):
        GitHubClient.parse_pr_url("https://gitlab.com/acme/app/-/merge_requests/123")


@pytest.mark.asyncio
async def test_no_token_raises():
    client = GitHubClient(token="")
    with pytest.raises(ValueError, match="GitHub token is required"):
        await client._request("GET", "/repos/acme/app/pulls/1")


@pytest.mark.asyncio
async def test_post_commit_status():
    """post_commit_status sends correct payload to GitHub statuses API."""
    client = GitHubClient(token="test-token")

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.headers = {"X-RateLimit-Remaining": "55"}
    mock_resp.json.return_value = {
        "id": 1,
        "state": "success",
        "context": "ACE Quality Gate",
        "description": "No issues found",
    }

    with patch.object(client, "_request", new=AsyncMock(return_value=mock_resp)) as mock_req:
        result = await client.post_commit_status(
            "acme",
            "app",
            "abc123",
            state="success",
            description="No issues found",
        )

    assert result["state"] == "success"
    assert result["context"] == "ACE Quality Gate"

    args, kwargs = mock_req.call_args
    assert args[0] == "POST"
    assert "/statuses/abc123" in args[1]
    payload = kwargs.get("json")
    assert payload["state"] == "success"
    assert payload["description"] == "No issues found"
    assert payload["context"] == "ACE Quality Gate"
    assert "target_url" not in payload


@pytest.mark.asyncio
async def test_post_commit_status_with_target_url():
    """post_commit_status includes target_url when provided."""
    client = GitHubClient(token="test-token")

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.headers = {"X-RateLimit-Remaining": "54"}
    mock_resp.json.return_value = {"id": 2, "state": "failure"}

    with patch.object(client, "_request", new=AsyncMock(return_value=mock_resp)) as mock_req:
        await client.post_commit_status(
            "acme",
            "app",
            "deadbeef",
            state="failure",
            description="2 findings",
            target_url="https://ace.example.com/reviews/42",
        )

    _, kwargs = mock_req.call_args
    payload = kwargs.get("json")
    assert payload["target_url"] == "https://ace.example.com/reviews/42"


@pytest.mark.asyncio
async def test_post_commit_status_truncates_description():
    """Descriptions longer than 140 chars are truncated."""
    client = GitHubClient(token="test-token")

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.headers = {"X-RateLimit-Remaining": "53"}
    mock_resp.json.return_value = {"id": 3, "state": "pending"}

    long_desc = "x" * 200

    with patch.object(client, "_request", new=AsyncMock(return_value=mock_resp)) as mock_req:
        await client.post_commit_status(
            "acme",
            "app",
            "sha999",
            state="pending",
            description=long_desc,
        )

    _, kwargs = mock_req.call_args
    payload = kwargs.get("json")
    assert len(payload["description"]) == 140


@pytest.mark.asyncio
async def test_fetch_file():
    """fetch_file returns file content on success."""
    client = GitHubClient(token="test-token")

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.headers = {"X-RateLimit-Remaining": "52"}
    mock_resp.text = "review:\n  gate:\n    critical_threshold: 0\n"

    with patch.object(client, "_request", new=AsyncMock(return_value=mock_resp)) as mock_req:
        content = await client.fetch_file("acme", "app", ".ace.yaml")

    assert content == "review:\n  gate:\n    critical_threshold: 0\n"

    args, kwargs = mock_req.call_args
    assert args[0] == "GET"
    assert "/contents/.ace.yaml" in args[1]
    assert kwargs.get("accept") == "application/vnd.github.raw+json"


@pytest.mark.asyncio
async def test_fetch_file_not_found():
    """fetch_file returns None when file doesn't exist (404)."""
    import httpx

    client = GitHubClient(token="test-token")

    # Build a realistic 404 HTTPStatusError
    not_found_resp = MagicMock(spec=httpx.Response)
    not_found_resp.status_code = 404
    http_error = httpx.HTTPStatusError("404 Not Found", request=MagicMock(), response=not_found_resp)

    with patch.object(client, "_request", new=AsyncMock(side_effect=http_error)):
        content = await client.fetch_file("acme", "app", ".ace.yaml")

    assert content is None


@pytest.mark.asyncio
async def test_fetch_file_propagates_non_404_errors():
    """fetch_file re-raises non-404 HTTP errors."""
    import httpx

    client = GitHubClient(token="test-token")

    server_error_resp = MagicMock(spec=httpx.Response)
    server_error_resp.status_code = 500
    http_error = httpx.HTTPStatusError("500 Server Error", request=MagicMock(), response=server_error_resp)

    with patch.object(client, "_request", new=AsyncMock(side_effect=http_error)):
        with pytest.raises(httpx.HTTPStatusError):
            await client.fetch_file("acme", "app", ".ace.yaml")
