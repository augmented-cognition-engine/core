# engine/pm/git.py
"""Git branch manager for work item isolation and milestone merges.

Branch pattern: ace/<init-id>/<ms-seq>/wi-<n>-<slug>
Integration branch: ace/<init-id>/m<seq>-integration
"""

from __future__ import annotations

import logging
import os
import re

from git import GitCommandError, Repo

logger = logging.getLogger(__name__)


def _slugify(text: str) -> str:
    """Convert text to URL-friendly slug."""
    slug = text.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug[:50].rstrip("-")


def predict_merge_conflicts(work_items: list[dict]) -> list[dict]:
    """Predict merge conflicts between parallel work items.

    Checks files_touched overlap (file-level) and directory-level overlap.
    Pure function — no git operations.
    """
    conflicts = []
    already_conflicting = set()

    for i, wi_a in enumerate(work_items):
        for wi_b in work_items[i + 1 :]:
            files_a = set(wi_a.get("files_touched") or [])
            files_b = set(wi_b.get("files_touched") or [])

            if not files_a or not files_b:
                continue

            overlap = files_a & files_b
            pair_key = (wi_a["id"], wi_b["id"])

            if overlap:
                conflicts.append(
                    {
                        "item_a": wi_a["id"],
                        "item_b": wi_b["id"],
                        "conflicting_files": sorted(overlap),
                        "recommendation": "run_sequentially",
                        "severity": "high",
                    }
                )
                already_conflicting.add(pair_key)
                continue

            # Directory-level overlap
            dirs_a = {os.path.dirname(f) for f in files_a if os.path.dirname(f)}
            dirs_b = {os.path.dirname(f) for f in files_b if os.path.dirname(f)}
            dir_overlap = dirs_a & dirs_b

            if dir_overlap and pair_key not in already_conflicting:
                conflicts.append(
                    {
                        "item_a": wi_a["id"],
                        "item_b": wi_b["id"],
                        "conflicting_dirs": sorted(dir_overlap),
                        "recommendation": "run_sequentially_or_review",
                        "severity": "low",
                    }
                )

    return conflicts


_HUNK_RE = re.compile(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
_DIFF_FILE_RE = re.compile(r"^diff --git a/.+ b/(.+)$")


def parse_changed_lines(diff_output: str) -> dict[str, set[int]]:
    """Parse git diff -U0 output into {filename: {line_numbers}}."""
    result: dict[str, set[int]] = {}
    current_file: str | None = None

    for line in diff_output.splitlines():
        file_match = _DIFF_FILE_RE.match(line)
        if file_match:
            current_file = file_match.group(1)
            if current_file not in result:
                result[current_file] = set()
            continue

        hunk_match = _HUNK_RE.match(line)
        if hunk_match and current_file:
            start = int(hunk_match.group(1))
            count = int(hunk_match.group(2)) if hunk_match.group(2) else 1
            result[current_file].update(range(start, start + count))

    return result


def compute_conflict_severity(
    lines_a: dict[str, set[int]],
    lines_b: dict[str, set[int]],
) -> tuple[str, list[dict]]:
    """Compare two branches' changed lines. Returns (severity, details)."""
    if not lines_a or not lines_b:
        return "none", []

    details = []
    max_sev = "none"

    files_a = set(lines_a.keys())
    files_b = set(lines_b.keys())
    common_files = files_a & files_b

    for f in sorted(common_files):
        overlap = lines_a[f] & lines_b[f]
        if overlap:
            details.append({"file": f, "overlapping_lines": sorted(overlap), "severity": "high"})
            max_sev = "high"
        else:
            details.append({"file": f, "overlapping_lines": [], "severity": "medium"})
            if max_sev != "high":
                max_sev = "medium"

    if max_sev == "none":
        dirs_a = {os.path.dirname(f) for f in files_a if os.path.dirname(f)}
        dirs_b = {os.path.dirname(f) for f in files_b if os.path.dirname(f)}
        if dirs_a & dirs_b:
            max_sev = "low"

    return max_sev, details


_SEVERITY_ORDER = {"high": 3, "medium": 2, "low": 1, "none": 0}


def max_severity(conflicts: list[dict]) -> str:
    """Return the highest severity across all conflicts."""
    if not conflicts:
        return "none"
    return max(
        conflicts,
        key=lambda c: _SEVERITY_ORDER.get(c.get("severity", "none"), 0),
    ).get("severity", "none")


def check_live_conflicts(
    initiative_id: str,
    milestone_seq: int,
    work_items: list[dict],
    repo_path: str,
) -> list[dict]:
    """Full live conflict check across WI branches.

    Uses branch naming convention: ace/<init-id>/<ms-seq>/wi-<n>-<slug>
    to locate branches and run pairwise git diff -U0 analysis.

    Returns list of {branch_a, branch_b, severity, details}.
    """
    repo = Repo(repo_path)

    # Find WI branches that exist
    init_id = initiative_id.split(":")[-1] if ":" in initiative_id else initiative_id
    prefix = f"ace/{init_id}/{milestone_seq}/"
    branch_names = [b.name for b in repo.branches if b.name.startswith(prefix)]

    if len(branch_names) < 2:
        return []

    # Get changed lines per branch vs base
    base = repo.active_branch.name
    branch_lines: dict[str, dict[str, set[int]]] = {}
    for branch in branch_names:
        try:
            diff_output = repo.git.diff("-U0", f"{base}...{branch}")
            branch_lines[branch] = parse_changed_lines(diff_output)
        except GitCommandError:
            branch_lines[branch] = {}

    # Pairwise comparison
    conflicts = []
    branch_list = list(branch_lines.keys())
    for i, branch_a in enumerate(branch_list):
        for branch_b in branch_list[i + 1 :]:
            severity, details = compute_conflict_severity(
                branch_lines[branch_a],
                branch_lines[branch_b],
            )
            if severity != "none":
                conflicts.append(
                    {
                        "branch_a": branch_a,
                        "branch_b": branch_b,
                        "severity": severity,
                        "details": details,
                    }
                )

    return conflicts


class GitBranchManager:
    """Manage git branches for work items and milestone merges."""

    def __init__(self, repo_path: str | None = None):
        self._repo_path = repo_path or os.getcwd()
        self._repo = Repo(self._repo_path)

    @property
    def repo(self) -> Repo:
        return self._repo

    def make_branch_name(
        self,
        initiative_id: str,
        milestone_seq: int,
        wi_index: int,
        wi_title: str,
    ) -> str:
        """Generate branch name: ace/<init-id>/<ms-seq>/wi-<n>-<slug>."""
        # Strip record prefix if present (e.g., "init:abc123" -> "abc123")
        init_id = initiative_id.split(":")[-1] if ":" in initiative_id else initiative_id
        slug = _slugify(wi_title)
        return f"ace/{init_id}/{milestone_seq}/wi-{wi_index}-{slug}"

    def create_branch(self, branch_name: str, from_branch: str | None = None) -> None:
        """Create a new branch from the specified base (or HEAD)."""
        if from_branch:
            base = self._repo.heads[from_branch]
        else:
            base = self._repo.active_branch
        self._repo.create_head(branch_name, base.commit)
        logger.info("Created branch %s from %s", branch_name, from_branch or "HEAD")

    def create_integration_branch(
        self,
        initiative_id: str,
        milestone_seq: int,
        from_branch: str | None = None,
    ) -> str:
        """Create milestone integration branch: ace/<init-id>/m<seq>-integration."""
        init_id = initiative_id.split(":")[-1] if ":" in initiative_id else initiative_id
        branch_name = f"ace/{init_id}/m{milestone_seq}-integration"
        self.create_branch(branch_name, from_branch=from_branch or self._repo.active_branch.name)
        return branch_name

    def merge_branch(self, source: str, into: str) -> dict:
        """Merge source branch into target. Returns success status and conflicts."""
        self._repo.heads[into].checkout()
        try:
            self._repo.git.merge(source)
            return {"success": True, "conflicts": []}
        except GitCommandError:
            # Check for conflict markers
            conflicts = []
            for item in self._repo.index.unmerged_blobs():
                conflicts.append(item)
            # Also check status for unmerged paths
            if not conflicts:
                unmerged = self._repo.git.diff("--name-only", "--diff-filter=U").strip()
                if unmerged:
                    conflicts = unmerged.split("\n")
            # Abort the failed merge
            try:
                self._repo.git.merge("--abort")
            except GitCommandError:
                pass
            return {"success": False, "conflicts": conflicts}

    def delete_branch(self, branch_name: str) -> None:
        """Delete a local branch."""
        if branch_name in [b.name for b in self._repo.branches]:
            self._repo.delete_head(branch_name, force=True)
            logger.info("Deleted branch %s", branch_name)

    def diff_files(self, branch: str, base: str) -> list[str]:
        """Get list of files changed between two branches."""
        diff = self._repo.git.diff("--name-only", base, branch)
        return [f for f in diff.strip().split("\n") if f]

    def cleanup_branches(self, initiative_id: str) -> list[str]:
        """Delete all branches for an initiative."""
        init_id = initiative_id.split(":")[-1] if ":" in initiative_id else initiative_id
        prefix = f"ace/{init_id}/"
        deleted = []
        for branch in list(self._repo.branches):
            if branch.name.startswith(prefix):
                if branch != self._repo.active_branch:
                    self._repo.delete_head(branch, force=True)
                    deleted.append(branch.name)
        return deleted

    def add_and_commit(self, message: str, files: list[str] | None = None) -> str:
        """Stage files and commit. Returns commit hash."""
        if files:
            self._repo.index.add(files)
        else:
            self._repo.git.add("-A")
        commit = self._repo.index.commit(message)
        return str(commit.hexsha)

    def add_worktree(self, path: str, branch: str, base_branch: str | None = None) -> None:
        """Create a git worktree at *path* on a new branch."""
        args = ["add", path, "-b", branch]
        if base_branch:
            args.append(base_branch)
        self._repo.git.worktree(*args)
        logger.info("Created worktree at %s on branch %s", path, branch)

    def remove_worktree(self, path: str, force: bool = False) -> None:
        """Remove a git worktree."""
        args = ["remove", path]
        if force:
            args.append("--force")
        self._repo.git.worktree(*args)
        logger.info("Removed worktree at %s", path)
