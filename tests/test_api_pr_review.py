# tests/test_api_pr_review.py
"""Tests for the PR review API endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from core.engine.api.main import app

    return TestClient(app)


def test_manual_review_endpoint_exists(client):
    resp = client.post("/review/pr", json={"pr_url": "https://github.com/acme/app/pull/1"})
    assert resp.status_code in (401, 403, 422)  # requires auth


def test_github_webhook_endpoint_exists(client):
    resp = client.post(
        "/webhooks/github",
        json={},
        headers={"X-GitHub-Event": "ping", "X-Hub-Signature-256": "sha256=test"},
    )
    assert resp.status_code != 404


def test_gitlab_webhook_endpoint_exists(client):
    resp = client.post(
        "/webhooks/gitlab",
        json={},
        headers={"X-Gitlab-Event": "Push Hook"},
    )
    assert resp.status_code != 404


def test_gitlab_webhook_ignores_non_mr_events(client):
    resp = client.post(
        "/webhooks/gitlab",
        json={},
        headers={"X-Gitlab-Event": "Push Hook"},
    )
    data = resp.json()
    assert data.get("status") == "ignored"


@pytest.mark.parametrize(
    ("path", "headers"),
    [
        ("/webhooks/github", {"X-GitHub-Event": "ping"}),
        ("/webhooks/gitlab", {"X-Gitlab-Event": "Push Hook"}),
    ],
)
def test_webhooks_fail_closed_without_provider_secret_outside_local_mode(client, monkeypatch, path, headers):
    from core.engine.api.pr_review import settings

    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "api_key", "test-api-key")
    monkeypatch.setattr(settings, "github_webhook_secret", "")
    monkeypatch.setattr(settings, "gitlab_webhook_secret", "")

    response = client.post(path, json={}, headers={**headers, "X-API-Key": "test-api-key"})

    assert response.status_code == 503
    assert "webhook authentication is not configured" in response.json()["detail"]


def test_quality_gate_endpoint_exists(client):
    with patch("core.engine.api.pr_review.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[[]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        resp = client.get("/review/gate/acme/app/1")

    assert resp.status_code == 200
    data = resp.json()
    assert data["pass_gate"] is True  # no review yet = pass by default


@pytest.mark.asyncio
async def test_review_comments_include_finding_indices():
    """Review comments should number findings for reaction tracking."""
    from core.engine.api.pr_review import _post_review_to_github
    from core.engine.github.client import GitHubClient
    from core.engine.review.models import ReviewFinding, ReviewSynthesis

    gh = MagicMock(spec=GitHubClient)
    gh.post_review = AsyncMock()

    synthesis = ReviewSynthesis(
        findings=[
            ReviewFinding(file="a.py", line=1, message="Issue 1", severity="high", discipline="security"),
            ReviewFinding(file="b.py", line=2, message="Issue 2", severity="medium", discipline="testing"),
        ],
        summary="2 findings",
        discipline_scores={"security": 0.8, "testing": 0.9},
        passes_run=2,
        findings_before_judge=2,
        findings_after_judge=2,
        pass_quality_gate=True,
    )

    await _post_review_to_github(gh, "owner", "repo", 42, synthesis)

    call_args = gh.post_review.call_args
    body = call_args.kwargs.get("body") or (call_args.args[3] if len(call_args.args) > 3 else "")
    assert "finding #0" in body.lower()
    assert "finding #1" in body.lower()
    # Footer with reaction API link should be present
    assert "reaction" in body.lower()
    assert "/review/reaction/owner/repo/42" in body
