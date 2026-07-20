"""GitHub REST API client — fetch PRs, diffs, post reviews.

Uses httpx for async HTTP, consistent with engine/core/search.py pattern.
"""

from __future__ import annotations

import logging
import re

import httpx

from core.engine.github.models import PRInfo

logger = logging.getLogger(__name__)

_PR_URL_RE = re.compile(r"https?://github\.com/([^/]+)/([^/]+)/pull/(\d+)")
_API_BASE = "https://api.github.com"


class GitHubClient:
    """Async GitHub API client for PR operations."""

    def __init__(self, token: str = ""):
        self.token = token

    @staticmethod
    def parse_pr_url(url: str) -> tuple[str, str, int]:
        """Extract (owner, repo, number) from a GitHub PR URL."""
        match = _PR_URL_RE.match(url)
        if not match:
            raise ValueError(f"Invalid GitHub PR URL: {url}")
        return match.group(1), match.group(2), int(match.group(3))

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
        accept: str = "application/vnd.github+json",
    ) -> httpx.Response:
        """Make an authenticated GitHub API request."""
        if not self.token:
            raise ValueError("GitHub token is required")

        async with httpx.AsyncClient(timeout=30) as http:
            resp = await http.request(
                method,
                f"{_API_BASE}{path}",
                json=json,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": accept,
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            resp.raise_for_status()
            remaining = resp.headers.get("X-RateLimit-Remaining", "1")
            if remaining == "0":
                logger.warning("GitHub API rate limit exhausted")
            return resp

    async def fetch_pr(self, owner: str, repo: str, pr_number: int) -> PRInfo:
        """Fetch PR metadata."""
        resp = await self._request("GET", f"/repos/{owner}/{repo}/pulls/{pr_number}")
        data = resp.json()
        return PRInfo(
            number=data["number"],
            title=data["title"],
            body=data.get("body") or "",
            author=data["user"]["login"],
            base_branch=data["base"]["ref"],
            head_branch=data["head"]["ref"],
            head_sha=data["head"]["sha"],
            repo_owner=owner,
            repo_name=repo,
            files_changed=data.get("changed_files", 0),
            additions=data.get("additions", 0),
            deletions=data.get("deletions", 0),
        )

    async def fetch_diff(self, owner: str, repo: str, pr_number: int) -> str:
        """Fetch the raw unified diff for a PR."""
        resp = await self._request(
            "GET",
            f"/repos/{owner}/{repo}/pulls/{pr_number}",
            accept="application/vnd.github.diff",
        )
        return resp.text

    async def post_review(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        body: str,
        comments: list[dict] | None = None,
        event: str = "COMMENT",
    ) -> dict:
        """Post a review on a PR. event: APPROVE | REQUEST_CHANGES | COMMENT"""
        payload: dict = {"body": body, "event": event}
        if comments:
            payload["comments"] = comments
        resp = await self._request(
            "POST",
            f"/repos/{owner}/{repo}/pulls/{pr_number}/reviews",
            json=payload,
        )
        return resp.json()

    async def fetch_files(self, owner: str, repo: str, pr_number: int) -> list[dict]:
        """Fetch the list of files changed in a PR with patch data."""
        resp = await self._request("GET", f"/repos/{owner}/{repo}/pulls/{pr_number}/files")
        return resp.json()

    async def post_commit_status(
        self,
        owner: str,
        repo: str,
        sha: str,
        state: str,
        description: str,
        context: str = "ACE Quality Gate",
        target_url: str | None = None,
    ) -> dict:
        """Post a commit status check. state: pending | success | failure | error"""
        payload: dict = {
            "state": state,
            "description": description[:140],  # GitHub limit
            "context": context,
        }
        if target_url:
            payload["target_url"] = target_url
        resp = await self._request(
            "POST",
            f"/repos/{owner}/{repo}/statuses/{sha}",
            json=payload,
        )
        return resp.json()

    async def fetch_file(self, owner: str, repo: str, path: str, ref: str = "main") -> str | None:
        """Fetch a file's content from a repo. Returns None if not found."""
        try:
            resp = await self._request(
                "GET",
                f"/repos/{owner}/{repo}/contents/{path}",
                accept="application/vnd.github.raw+json",
            )
            return resp.text
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise
