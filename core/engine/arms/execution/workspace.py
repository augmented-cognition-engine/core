"""Workspace — a throwaway git worktree on a fresh branch. Reversible by discard();
provenance-checked so we never remove a worktree we didn't create."""

from __future__ import annotations

import logging
import os
import subprocess
import uuid

from core.engine.arms.base import PromotionRequest

logger = logging.getLogger(__name__)


def _git_root() -> str:
    out = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True)
    return out.stdout.strip()


class Workspace:
    def __init__(self, path: str, branch: str, repo_root: str, created_by_runtime: bool = True):
        self.path = path
        self.branch = branch
        self.repo_root = repo_root
        self.created_by_runtime = created_by_runtime

    @classmethod
    def create(cls, label: str = "arm", repo_root: str | None = None) -> "Workspace":
        repo_root = repo_root or _git_root()
        wid = uuid.uuid4().hex[:8]
        branch = f"arm/{label}-{wid}"
        path = os.path.join(repo_root, ".worktrees", f"arm-{wid}")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        subprocess.run(
            ["git", "-C", repo_root, "worktree", "add", "-b", branch, path, "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return cls(path, branch, repo_root)

    def _track_new_files(self) -> None:
        """`git add -N` the untracked files so git will render them in a diff.

        Load-bearing, and it was missing: plain `git diff` reports only TRACKED, unstaged changes,
        while arms mostly CREATE files. So every build whose work was new files reported an empty
        diff — an empty diff_summary on action_outcome, zero `outcome_touches` edges (the graph
        believed those builds touched nothing), and an adversarial critic reviewing a blank page.

        `add -N` (intent-to-add) registers the path WITHOUT staging content, which is exactly what
        we want: the diff renders in full and nothing is committed. Scoped with -C to the isolated
        worktree, which contains only the HEAD checkout plus what this arm just wrote — never the
        main repo's standing untracked work.

        Non-fatal: if this fails we simply fall back to the tracked-only diff.
        """
        try:
            subprocess.run(["git", "-C", self.path, "add", "-N", "."], capture_output=True, text=True, check=False)
        except Exception as exc:
            logger.warning("workspace intent-to-add failed (non-fatal, new files may be invisible): %s", exc)

    def diff(self) -> str:
        """The full diff of this worktree against HEAD — INCLUDING newly created files."""
        self._track_new_files()
        out = subprocess.run(["git", "-C", self.path, "diff"], capture_output=True, text=True)
        return out.stdout

    def changed_files(self) -> list[str]:
        """Paths changed in this worktree, created files included. The clean source for afferent
        `touches` edges — diff() text is truncated for diff_summary and can't be parsed for a full
        list. Non-fatal: returns [] on any git error."""
        try:
            self._track_new_files()
            out = subprocess.run(["git", "-C", self.path, "diff", "--name-only"], capture_output=True, text=True)
            return [line.strip() for line in (out.stdout or "").splitlines() if line.strip()]
        except Exception as exc:
            logger.warning("workspace changed_files failed (non-fatal): %s", exc)
            return []

    def commit(self, message: str) -> str | None:
        """Commit everything in this worktree onto its branch. Returns the sha, or None if there was
        nothing to commit.

        Without this the arm's work exists ONLY as uncommitted files in a temporary worktree — the
        branch carries nothing. Promotion then runs `git merge <branch>`, is told "Already up to
        date", exits 0, and reports a SUCCESSFUL PROMOTION having shipped absolutely nothing. The
        spec gets marked shipped. The diff evaporates. Every gate passes.

        Build #7 — the first build ACE ever completed — did exactly this: verified, critic-approved,
        and left a branch with nothing on it.

        `add -A` is scoped to the worktree, which contains only the HEAD checkout plus what this arm
        just wrote. (The standing "never `git add -A`" rule is about the MAIN repo, which carries
        untracked work that must never be swept up. This is an isolated, throwaway checkout.)
        """
        try:
            subprocess.run(["git", "-C", self.path, "add", "-A"], capture_output=True, text=True, check=True)
            staged = subprocess.run(
                ["git", "-C", self.path, "diff", "--cached", "--name-only"], capture_output=True, text=True
            ).stdout.strip()
            if not staged:
                return None  # nothing changed — say so, do not fake a commit
            subprocess.run(
                ["git", "-C", self.path, "commit", "-q", "-m", message],
                capture_output=True,
                text=True,
                check=True,
            )
            sha = subprocess.run(
                ["git", "-C", self.path, "rev-parse", "HEAD"], capture_output=True, text=True
            ).stdout.strip()
            logger.info("committed %s onto %s (%s)", staged.replace("\n", ", ")[:120], self.branch, sha[:8])
            return sha or None
        except Exception as exc:
            logger.warning("workspace commit failed: %s", exc)
            return None

    def promote_request(self, target: str = "master") -> PromotionRequest:
        """Surface — NEVER merge. The human approves the promotion."""
        d = self.diff()
        return PromotionRequest(branch=self.branch, diff_summary=d[:500], target=target)

    def discard(self) -> None:
        """Provenance-checked + idempotent. Runs from repo_root (never inside the worktree)."""
        if not self.created_by_runtime:
            return
        try:
            subprocess.run(
                ["git", "-C", self.repo_root, "worktree", "remove", "--force", self.path],
                capture_output=True,
                text=True,
            )
            subprocess.run(["git", "-C", self.repo_root, "branch", "-D", self.branch], capture_output=True, text=True)
            subprocess.run(["git", "-C", self.repo_root, "worktree", "prune"], capture_output=True, text=True)
        except Exception as exc:
            logger.warning("workspace discard failed (non-fatal): %s", exc)
