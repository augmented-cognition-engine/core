"""Git provider adapters — abstract the diff source for platform-agnostic review.

The review engine works on FileDiff objects. This module provides adapters
to fetch diffs from different sources: local git, GitHub, GitLab.
"""

from __future__ import annotations

import logging
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path

from core.engine.github.diff_parser import parse_diff
from core.engine.github.models import FileDiff, PRInfo

logger = logging.getLogger(__name__)


class GitProvider(ABC):
    """Abstract interface for fetching PR/MR/branch diffs."""

    @abstractmethod
    async def get_diff(self) -> tuple[PRInfo, list[FileDiff]]:
        """Fetch PR info and parsed file diffs."""
        ...

    @abstractmethod
    async def post_review(self, synthesis) -> None:
        """Post review results back to the platform (no-op for local)."""
        ...

    @abstractmethod
    async def post_status(self, state: str, description: str) -> None:
        """Post a status check (no-op for local)."""
        ...


class LocalGitProvider(GitProvider):
    """Review local git branches by running git diff.

    Compares a feature branch against a base branch (default: main).
    No PR posting — outputs review results to the caller.
    """

    def __init__(self, repo_path: str = ".", base_branch: str = "main", head_branch: str | None = None):
        self.repo_path = Path(repo_path).resolve()
        self.base_branch = base_branch
        self.head_branch = head_branch  # None = current branch

    async def get_diff(self) -> tuple[PRInfo, list[FileDiff]]:
        """Get diff between base and head branch using local git."""
        head = self.head_branch or _get_current_branch(self.repo_path)
        diff_text = _run_git(self.repo_path, "diff", f"{self.base_branch}...{head}")
        files = parse_diff(diff_text)

        # Count stats
        additions = sum(f.additions for f in files)
        deletions = sum(f.deletions for f in files)

        pr = PRInfo(
            number=0,  # no PR number for local
            title=f"{head} → {self.base_branch}",
            body="",
            author=_run_git(self.repo_path, "config", "user.name").strip(),
            base_branch=self.base_branch,
            head_branch=head,
            files_changed=len(files),
            additions=additions,
            deletions=deletions,
        )
        return pr, files

    async def post_review(self, synthesis) -> None:
        """No-op for local git — review is returned to caller."""
        pass

    async def post_status(self, state: str, description: str) -> None:
        """No-op for local git."""
        pass


class GitHubProvider(GitProvider):
    """Review GitHub PRs via the GitHub API."""

    def __init__(self, owner: str, repo: str, pr_number: int, token: str = ""):
        from core.engine.core.config import settings
        from core.engine.github.client import GitHubClient

        self.owner = owner
        self.repo = repo
        self.pr_number = pr_number
        self.gh = GitHubClient(token=token or settings.github_token)
        self._pr: PRInfo | None = None

    async def get_diff(self) -> tuple[PRInfo, list[FileDiff]]:
        pr = await self.gh.fetch_pr(self.owner, self.repo, self.pr_number)
        self._pr = pr
        diff_text = await self.gh.fetch_diff(self.owner, self.repo, self.pr_number)
        files = parse_diff(diff_text)
        return pr, files

    async def post_review(self, synthesis) -> None:
        from core.engine.api.pr_review import _post_review_to_github

        await _post_review_to_github(self.gh, self.owner, self.repo, self.pr_number, synthesis)

    async def post_status(self, state: str, description: str) -> None:
        if self._pr and self._pr.head_sha:
            await self.gh.post_commit_status(
                self.owner,
                self.repo,
                self._pr.head_sha,
                state=state,
                description=description,
            )


class GitLabProvider(GitProvider):
    """Review GitLab merge requests via the GitLab API."""

    def __init__(self, project_id: str, mr_iid: int, token: str = "", base_url: str = "https://gitlab.com"):
        self.project_id = project_id  # e.g. "group/project" or numeric ID
        self.mr_iid = mr_iid
        self.token = token
        self.base_url = base_url.rstrip("/")
        self._mr_data: dict | None = None

    async def get_diff(self) -> tuple[PRInfo, list[FileDiff]]:
        import httpx

        headers = {"PRIVATE-TOKEN": self.token} if self.token else {}
        encoded_project = self.project_id.replace("/", "%2F")

        async with httpx.AsyncClient(timeout=30) as client:
            # Fetch MR metadata
            mr_resp = await client.get(
                f"{self.base_url}/api/v4/projects/{encoded_project}/merge_requests/{self.mr_iid}",
                headers=headers,
            )
            mr_resp.raise_for_status()
            mr = mr_resp.json()
            self._mr_data = mr

            # Fetch MR diff (changes endpoint gives structured diffs)
            changes_resp = await client.get(
                f"{self.base_url}/api/v4/projects/{encoded_project}/merge_requests/{self.mr_iid}/changes",
                headers=headers,
            )
            changes_resp.raise_for_status()
            changes = changes_resp.json()

        # Build unified diff from GitLab's changes format
        diff_parts = []
        for change in changes.get("changes", []):
            diff_text = change.get("diff", "")
            old_path = change.get("old_path", "")
            new_path = change.get("new_path", "")
            if diff_text:
                header = f"diff --git a/{old_path} b/{new_path}\n"
                if change.get("new_file"):
                    header += "new file mode 100644\n"
                elif change.get("deleted_file"):
                    header += "deleted file mode 100644\n"
                elif change.get("renamed_file"):
                    header += f"rename from {old_path}\nrename to {new_path}\n"
                header += f"--- a/{old_path}\n+++ b/{new_path}\n"
                diff_parts.append(header + diff_text)

        files = parse_diff("\n".join(diff_parts))

        pr = PRInfo(
            number=mr.get("iid", self.mr_iid),
            title=mr.get("title", ""),
            body=mr.get("description", "") or "",
            author=mr.get("author", {}).get("username", ""),
            base_branch=mr.get("target_branch", "main"),
            head_branch=mr.get("source_branch", ""),
            head_sha=mr.get("sha", ""),
            repo_owner=self.project_id.split("/")[0] if "/" in self.project_id else "",
            repo_name=self.project_id.split("/")[-1] if "/" in self.project_id else self.project_id,
            files_changed=len(files),
            additions=sum(f.additions for f in files),
            deletions=sum(f.deletions for f in files),
        )
        return pr, files

    async def post_review(self, synthesis) -> None:
        """Post review as MR note (comment) on GitLab."""
        import httpx

        if not self.token:
            return

        headers = {"PRIVATE-TOKEN": self.token}
        encoded_project = self.project_id.replace("/", "%2F")

        # Build review body
        lines = ["## ACE Code Review", ""]
        if synthesis.gate_failures:
            lines.append("**Quality gate: FAILED**")
            for f in synthesis.gate_failures:
                lines.append(f"- {f}")
        else:
            lines.append("**Quality gate: PASSED**")
        lines.append("")
        if synthesis.summary:
            lines.append(synthesis.summary)
            lines.append("")

        if synthesis.findings:
            lines.append(f"### Findings ({len(synthesis.findings)})")
            for i, finding in enumerate(synthesis.findings[:20]):
                severity_tag = finding.severity.upper()
                lines.append(
                    f"- **[{severity_tag}]** `{finding.file}:{finding.line}` — {finding.message} _(finding #{i})_"
                )
                if finding.suggested_fix:
                    lines.append(f"  - Suggestion: {finding.suggested_fix}")
            if len(synthesis.findings) > 20:
                lines.append(f"  - _(and {len(synthesis.findings) - 20} more…)_")

        lines.append("")
        lines.append("---")
        lines.append(
            f"_ACE Review • {len(synthesis.findings)} findings across {len(synthesis.discipline_scores)} disciplines_"
        )

        body = "\n".join(lines)

        async with httpx.AsyncClient(timeout=30) as client:
            await client.post(
                f"{self.base_url}/api/v4/projects/{encoded_project}/merge_requests/{self.mr_iid}/notes",
                headers=headers,
                json={"body": body},
            )

    async def post_status(self, state: str, description: str) -> None:
        """Post commit status on GitLab."""
        import httpx

        if not self.token or not self._mr_data:
            return

        headers = {"PRIVATE-TOKEN": self.token}
        encoded_project = self.project_id.replace("/", "%2F")
        sha = self._mr_data.get("sha", "")

        # GitLab uses different state names
        gl_state_map = {"pending": "pending", "success": "success", "failure": "failed", "error": "failed"}

        if sha:
            async with httpx.AsyncClient(timeout=30) as client:
                await client.post(
                    f"{self.base_url}/api/v4/projects/{encoded_project}/statuses/{sha}",
                    headers=headers,
                    json={
                        "state": gl_state_map.get(state, state),
                        "description": description[:140],
                        "name": "ACE Quality Gate",
                    },
                )


def _run_git(repo_path: Path, *args: str) -> str:
    """Run a git command and return stdout."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            logger.warning("git %s failed: %s", " ".join(args), result.stderr.strip())
            return ""
        return result.stdout
    except Exception as exc:
        logger.warning("git command failed: %s", exc)
        return ""


def _get_current_branch(repo_path: Path) -> str:
    """Get the current branch name."""
    return _run_git(repo_path, "rev-parse", "--abbrev-ref", "HEAD").strip() or "HEAD"


def create_provider(source: str, **kwargs) -> GitProvider:
    """Factory: create the right provider from a source string.

    source formats:
    - "local" or "local:/path/to/repo" — local git diff
    - "github:owner/repo#123" or GitHub PR URL — GitHub PR
    - "gitlab:project/path!42" — GitLab MR
    - "gitlab:https://gitlab.example.com/project!42" — self-hosted GitLab
    """
    if source == "local" or source.startswith("local:"):
        repo_path = source.split(":", 1)[1] if ":" in source else "."
        return LocalGitProvider(
            repo_path=repo_path,
            base_branch=kwargs.get("base_branch", "main"),
            head_branch=kwargs.get("head_branch"),
        )

    if source.startswith("https://github.com/") or source.startswith("github:"):
        if source.startswith("https://"):
            from core.engine.github.client import GitHubClient

            owner, repo, number = GitHubClient.parse_pr_url(source)
        else:
            # github:owner/repo#123
            ref = source.split(":", 1)[1]
            repo_part, _, number_str = ref.partition("#")
            owner, repo = repo_part.split("/", 1)
            number = int(number_str)
        return GitHubProvider(owner, repo, number, token=kwargs.get("token", ""))

    if source.startswith("gitlab:"):
        ref = source.split(":", 1)[1]
        # Handle self-hosted: gitlab:https://gitlab.example.com/group/project!42
        if ref.startswith("https://"):
            # Extract base_url and project!mr_iid
            parts = ref.split("/")
            base_url = "/".join(parts[:3])  # https://gitlab.example.com
            rest = "/".join(parts[3:])  # group/project!42
            project_part, _, mr_str = rest.rpartition("!")
            return GitLabProvider(
                project_id=project_part,
                mr_iid=int(mr_str),
                token=kwargs.get("token", ""),
                base_url=base_url,
            )
        else:
            # gitlab:group/project!42
            project_part, _, mr_str = ref.rpartition("!")
            return GitLabProvider(
                project_id=project_part,
                mr_iid=int(mr_str),
                token=kwargs.get("token", ""),
            )

    raise ValueError(f"Unknown source format: {source}")
