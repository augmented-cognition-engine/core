# engine/atc/landing.py
"""Landing Sequence — ordered merge queue with rebase-before-merge.

The single-runway model: all merges to a given branch go through a queue.
One merge at a time. Each flight rebases onto the latest target before
merging, guaranteeing no overwrites.

Usage:
    landing = LandingSequence(repo_path="/path/to/repo")
    result = await landing.land(flight_id, source_branch, target_branch, product_id)
    # result: {success, conflicts, rebased, commit_sha}
"""

from __future__ import annotations

import asyncio
import logging

from git import GitCommandError, Repo

logger = logging.getLogger(__name__)

# One lock per target branch — ensures sequential landing
_runway_locks: dict[str, asyncio.Lock] = {}


def _get_runway_lock(target_branch: str) -> asyncio.Lock:
    """Get or create a lock for a target branch (runway)."""
    if target_branch not in _runway_locks:
        _runway_locks[target_branch] = asyncio.Lock()
    return _runway_locks[target_branch]


class LandingSequence:
    """Ordered merge queue with rebase-before-merge.

    Ensures merges to the same branch are sequential. Each flight
    rebases onto the latest target state before merging, so every
    merge sees the full history including prior landings.
    """

    def __init__(self, repo_path: str | None = None):
        import os

        self._repo_path = repo_path or os.getcwd()
        self._repo = Repo(self._repo_path)

    async def land(
        self,
        source_branch: str,
        target_branch: str,
        flight_id: str | None = None,
    ) -> dict:
        """Land a flight: rebase source onto target, then merge.

        Acquires a per-branch lock so only one landing happens at a time.
        Returns {success, conflicts, rebased, commit_sha, flight_id}.
        """
        lock = _get_runway_lock(target_branch)

        async with lock:
            return await self._do_land(source_branch, target_branch, flight_id)

    async def _do_land(
        self,
        source_branch: str,
        target_branch: str,
        flight_id: str | None,
    ) -> dict:
        """Execute the actual rebase + merge sequence."""
        result = {
            "success": False,
            "conflicts": [],
            "rebased": False,
            "commit_sha": None,
            "flight_id": flight_id,
            "source_branch": source_branch,
            "target_branch": target_branch,
        }

        try:
            # 1. Checkout source branch
            self._repo.heads[source_branch].checkout()

            # 2. Rebase onto latest target
            try:
                self._repo.git.rebase(target_branch)
                result["rebased"] = True
                logger.info("Rebased %s onto %s", source_branch, target_branch)
            except GitCommandError:
                # Rebase conflict — abort and report
                try:
                    self._repo.git.rebase("--abort")
                except GitCommandError:
                    pass

                # Get conflicting files
                conflicts = self._get_conflict_files()
                result["conflicts"] = conflicts
                logger.warning(
                    "Rebase conflict: %s onto %s — %d files",
                    source_branch,
                    target_branch,
                    len(conflicts),
                )

                # Checkout target to leave repo in clean state
                self._repo.heads[target_branch].checkout()
                return result

            # 3. Merge into target (fast-forward after rebase)
            self._repo.heads[target_branch].checkout()
            try:
                self._repo.git.merge(source_branch, "--ff-only")
                result["success"] = True
                result["commit_sha"] = str(self._repo.head.commit.hexsha)
                logger.info(
                    "Landed %s → %s (commit: %s)",
                    source_branch,
                    target_branch,
                    result["commit_sha"][:8],
                )
            except GitCommandError:
                # Fall back to regular merge if ff not possible
                try:
                    self._repo.git.merge(source_branch)
                    result["success"] = True
                    result["commit_sha"] = str(self._repo.head.commit.hexsha)
                except GitCommandError:
                    conflicts = self._get_conflict_files()
                    result["conflicts"] = conflicts
                    try:
                        self._repo.git.merge("--abort")
                    except GitCommandError:
                        pass

        except Exception as exc:
            logger.error("Landing failed for %s: %s", source_branch, exc)
            result["conflicts"] = [str(exc)]
            # Try to leave repo in clean state
            try:
                self._repo.heads[target_branch].checkout()
            except Exception:
                pass

        return result

    def _get_conflict_files(self) -> list[str]:
        """Extract conflicting file paths from git status."""
        try:
            unmerged = self._repo.git.diff("--name-only", "--diff-filter=U").strip()
            if unmerged:
                return unmerged.split("\n")
        except GitCommandError:
            pass
        return []

    async def preview_landing(self, source_branch: str, target_branch: str) -> dict:
        """Preview what a landing would look like without doing it.

        Returns the list of files that would change and any potential conflicts.
        """
        try:
            # Files that would change
            diff_files = self._repo.git.diff("--name-only", target_branch, source_branch).strip()
            files = [f for f in diff_files.split("\n") if f] if diff_files else []

            # Check if rebase would conflict (dry-run not available in git,
            # so we check merge-base divergence as a heuristic)
            merge_base = self._repo.git.merge_base(source_branch, target_branch).strip()
            target_head = str(self._repo.heads[target_branch].commit.hexsha)
            diverged = merge_base != target_head

            return {
                "files_changed": files,
                "file_count": len(files),
                "diverged": diverged,
                "merge_base": merge_base[:8],
                "potential_conflicts": diverged,
            }

        except Exception as exc:
            return {
                "files_changed": [],
                "file_count": 0,
                "diverged": False,
                "error": str(exc),
            }
