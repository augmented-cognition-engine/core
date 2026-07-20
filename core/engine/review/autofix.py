# engine/review/autofix.py
"""Auto-fix PR generation — turns review findings into fix PRs.

When ACE review finds critical or high-severity issues with suggested fixes,
this agent generates a fix branch and creates a PR.
"""

from __future__ import annotations

import base64
import logging

from core.engine.core.config import settings
from core.engine.core.llm import llm
from core.engine.github.client import GitHubClient
from core.engine.review.models import ReviewFinding, ReviewSynthesis

logger = logging.getLogger(__name__)


class AutofixAgent:
    """Generates fix PRs from review findings."""

    def __init__(self, gh: GitHubClient | None = None):
        self.gh = gh or GitHubClient(token=settings.github_token)

    def should_autofix(self, synthesis: ReviewSynthesis) -> bool:
        """Determine if autofix should run based on findings."""
        fixable = [f for f in synthesis.findings if f.severity in ("critical", "high") and f.suggested_fix]
        return len(fixable) > 0

    def get_fixable_findings(self, synthesis: ReviewSynthesis) -> list[ReviewFinding]:
        """Get findings that have suggested fixes and are high severity."""
        return [f for f in synthesis.findings if f.severity in ("critical", "high") and f.suggested_fix]

    async def generate_fix(self, finding: ReviewFinding, file_content: str) -> str | None:
        """Use LLM to generate a fixed version of the file.

        Returns the full fixed file content, or None if fix generation fails.
        """
        prompt = f"""You are a code fixer. Apply this specific fix to the file.

## Issue
File: {finding.file}
Line: {finding.line}
Problem: {finding.message}
Suggested fix: {finding.suggested_fix}
Severity: {finding.severity}
Discipline: {finding.discipline}

## Current File Content
```
{file_content}
```

## Instructions
- Apply ONLY the suggested fix. Do not make any other changes.
- Return the COMPLETE fixed file content.
- Preserve all existing formatting, imports, and structure.
- Do not add comments about the fix.

Return ONLY the fixed file content, no explanation."""

        try:
            response = await llm.complete(prompt, model=settings.llm_budget_model)
            # Strip markdown code fences if present
            content = response.strip()
            if content.startswith("```"):
                lines = content.split("\n")
                # Remove first line (```python or ```) and last line (```)
                if lines[-1].strip() == "```":
                    lines = lines[1:-1]
                else:
                    lines = lines[1:]
                content = "\n".join(lines)
            return content
        except Exception as exc:
            logger.warning("Fix generation failed for %s:%d: %s", finding.file, finding.line, exc)
            return None

    async def create_fix_pr(
        self,
        owner: str,
        repo: str,
        base_branch: str,
        pr_number: int,
        findings: list[ReviewFinding],
        fixes: dict[str, str],  # file_path -> fixed_content
    ) -> dict | None:
        """Create a PR with the fixes applied.

        Uses GitHub's API to:
        1. Get the base branch ref
        2. Create a new branch
        3. Update files with fixes
        4. Create a PR

        Returns the created PR data or None on failure.
        """
        branch_name = f"ace/fix-{pr_number}"

        try:
            # Get base branch SHA
            resp = await self.gh._request("GET", f"/repos/{owner}/{repo}/git/ref/heads/{base_branch}")
            base_sha = resp.json()["object"]["sha"]

            # Create branch
            try:
                await self.gh._request(
                    "POST",
                    f"/repos/{owner}/{repo}/git/refs",
                    json={"ref": f"refs/heads/{branch_name}", "sha": base_sha},
                )
            except Exception:
                # Branch may already exist — try to update it
                await self.gh._request(
                    "PATCH",
                    f"/repos/{owner}/{repo}/git/refs/heads/{branch_name}",
                    json={"sha": base_sha, "force": True},
                )

            # Apply fixes by updating files
            for file_path, content in fixes.items():
                # Get current file to get its SHA
                try:
                    file_resp = await self.gh._request(
                        "GET",
                        f"/repos/{owner}/{repo}/contents/{file_path}",
                        accept="application/vnd.github+json",
                    )
                    file_sha = file_resp.json().get("sha", "")
                except Exception:
                    file_sha = ""

                encoded = base64.b64encode(content.encode()).decode()

                update_payload = {
                    "message": f"fix: {findings[0].message[:50]}",
                    "content": encoded,
                    "branch": branch_name,
                }
                if file_sha:
                    update_payload["sha"] = file_sha

                await self.gh._request(
                    "PUT",
                    f"/repos/{owner}/{repo}/contents/{file_path}",
                    json=update_payload,
                )

            # Create PR
            finding_list = "\n".join(
                f"- **[{f.severity.upper()}]** `{f.file}:{f.line}` — {f.message}" for f in findings
            )
            pr_body = f"""## ACE Auto-Fix

Automated fixes for issues found in PR #{pr_number}.

### Findings Addressed
{finding_list}

---
Generated by ACE PR Review Agent
"""

            resp = await self.gh._request(
                "POST",
                f"/repos/{owner}/{repo}/pulls",
                json={
                    "title": f"fix: ACE auto-fix for #{pr_number}",
                    "body": pr_body,
                    "head": branch_name,
                    "base": base_branch,
                },
            )
            return resp.json()

        except Exception as exc:
            logger.error("Failed to create fix PR for %s/%s#%d: %s", owner, repo, pr_number, exc)
            return None

    async def create_fix_mr(
        self,
        project_id: str,
        base_branch: str,
        mr_iid: int,
        findings: list[ReviewFinding],
        fixes: dict[str, str],
        token: str = "",
        base_url: str = "https://gitlab.com",
    ) -> dict | None:
        """Create a GitLab MR with the fixes applied.

        Uses GitLab's Commits API to create a branch + commit, then the
        Merge Requests API to open the fix MR.
        """
        import httpx

        branch_name = f"ace/fix-{mr_iid}"
        headers = {"PRIVATE-TOKEN": token} if token else {}
        encoded_project = project_id.replace("/", "%2F")
        api = f"{base_url.rstrip('/')}/api/v4/projects/{encoded_project}"

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                # Build commit actions (one per fixed file)
                actions = []
                for file_path, content in fixes.items():
                    actions.append(
                        {
                            "action": "update",
                            "file_path": file_path,
                            "content": content,
                        }
                    )

                # Create branch + commit in a single API call
                commit_resp = await client.post(
                    f"{api}/repository/commits",
                    headers=headers,
                    json={
                        "branch": branch_name,
                        "start_branch": base_branch,
                        "commit_message": f"fix: ACE auto-fix for !{mr_iid}",
                        "actions": actions,
                    },
                )
                commit_resp.raise_for_status()

                # Create merge request
                finding_list = "\n".join(
                    f"- **[{f.severity.upper()}]** `{f.file}:{f.line}` — {f.message}" for f in findings
                )
                mr_resp = await client.post(
                    f"{api}/merge_requests",
                    headers=headers,
                    json={
                        "source_branch": branch_name,
                        "target_branch": base_branch,
                        "title": f"fix: ACE auto-fix for !{mr_iid}",
                        "description": (
                            f"## ACE Auto-Fix\n\n"
                            f"Automated fixes for issues found in MR !{mr_iid}.\n\n"
                            f"### Findings Addressed\n{finding_list}\n\n"
                            f"---\nGenerated by ACE PR Review Agent"
                        ),
                    },
                )
                mr_resp.raise_for_status()
                return mr_resp.json()

        except Exception as exc:
            logger.error("Failed to create fix MR for %s!%d: %s", project_id, mr_iid, exc)
            return None

    async def apply_local_fixes(
        self,
        repo_path: str,
        synthesis: ReviewSynthesis,
        branch_name: str | None = None,
    ) -> dict:
        """Apply fixes locally — optionally on a new branch.

        If branch_name is provided, creates a new branch first.
        Returns dict with files_fixed, files, and branch info.
        """
        import subprocess
        from pathlib import Path

        repo = Path(repo_path)
        fixable = self.get_fixable_findings(synthesis)
        if not fixable:
            return {"files_fixed": 0, "files": [], "branch": branch_name}

        # Optionally create branch
        if branch_name:
            result = subprocess.run(
                ["git", "checkout", "-b", branch_name],
                cwd=repo,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                logger.warning("Failed to create branch %s: %s", branch_name, result.stderr.strip())
                branch_name = None  # Continue without branch if creation fails

        # Group findings by file (use first fixable finding per file)
        by_file: dict[str, ReviewFinding] = {}
        for f in fixable:
            if f.file not in by_file:
                by_file[f.file] = f

        fixed_files = []
        for file_rel, finding in by_file.items():
            file_path = repo / file_rel
            if not file_path.exists():
                logger.warning("File not found for local autofix: %s", file_path)
                continue
            content = file_path.read_text()
            fixed = await self.generate_fix(finding, content)
            if fixed and fixed != content:
                file_path.write_text(fixed)
                fixed_files.append(file_rel)

        # Stage and commit if fixes were applied
        if fixed_files:
            subprocess.run(
                ["git", "add"] + fixed_files,
                cwd=repo,
                capture_output=True,
            )
            msg = f"fix: ACE auto-fix — {len(fixed_files)} file(s)"
            subprocess.run(
                ["git", "commit", "-m", msg],
                cwd=repo,
                capture_output=True,
            )

        return {
            "files_fixed": len(fixed_files),
            "files": fixed_files,
            "branch": branch_name,
        }

    async def run(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        base_branch: str,
        synthesis: ReviewSynthesis,
    ) -> dict | None:
        """Full autofix pipeline: select findings → generate fixes → create PR."""
        fixable = self.get_fixable_findings(synthesis)
        if not fixable:
            return None

        # Group findings by file
        by_file: dict[str, list[ReviewFinding]] = {}
        for f in fixable:
            by_file.setdefault(f.file, []).append(f)

        # Generate fixes per file
        fixes: dict[str, str] = {}
        all_findings: list[ReviewFinding] = []

        for file_path, file_findings in by_file.items():
            # Fetch current file content
            content = await self.gh.fetch_file(owner, repo, file_path, ref=base_branch)
            if content is None:
                logger.warning("Cannot fetch %s for autofix", file_path)
                continue

            # Use the first finding's fix (simplest approach)
            # Future: chain fixes for multiple findings in same file
            fixed = await self.generate_fix(file_findings[0], content)
            if fixed and fixed != content:
                fixes[file_path] = fixed
                all_findings.extend(file_findings)

        if not fixes:
            logger.info("No fixes generated for %s/%s#%d", owner, repo, pr_number)
            return None

        return await self.create_fix_pr(owner, repo, base_branch, pr_number, all_findings, fixes)
