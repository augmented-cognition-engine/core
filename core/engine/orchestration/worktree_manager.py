# engine/orchestration/worktree_manager.py
"""Worktree Manager — git worktree lifecycle for parallel agent isolation.

Each parallel agent gets its own worktree (isolated copy of the repo).
When the batch completes, worktrees merge into an integration branch
and are cleaned up.

Uses GitBranchManager for branch operations, adds the worktree layer on top.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field

from git import GitCommandError

logger = logging.getLogger(__name__)


@dataclass
class WorktreeInfo:
    """Metadata for an active worktree."""

    unit_id: str
    worktree_path: str
    branch_name: str
    created_at: float = field(default_factory=time.monotonic)


class WorktreeManager:
    """Manage git worktrees for parallel agent execution.

    Lifecycle:
    1. create_for_batch() — one worktree per unit in a parallel batch
    2. (agents execute in their worktrees)
    3. merge_batch() — merge unit branches into an integration branch
    4. cleanup_batch() — remove worktrees and branches
    """

    def __init__(self, repo_path: str | None = None):
        from core.engine.pm.git import GitBranchManager

        self._repo_path = repo_path or os.getcwd()
        self._git = GitBranchManager(repo_path=self._repo_path)
        self._worktree_base = os.path.join(self._repo_path, ".worktrees")
        self._active: dict[str, WorktreeInfo] = {}

    async def create_for_batch(
        self,
        batch_unit_ids: list[str],
        base_branch: str | None = None,
    ) -> dict[str, WorktreeInfo]:
        """Create one worktree per unit in a parallel batch.

        Each worktree gets its own branch (atc/<unit_id>) forked from
        base_branch (or HEAD).
        """
        os.makedirs(self._worktree_base, exist_ok=True)

        base = base_branch or self._git.repo.active_branch.name
        result: dict[str, WorktreeInfo] = {}

        for uid in batch_unit_ids:
            branch_name = f"atc/{uid}"
            worktree_path = os.path.join(self._worktree_base, uid)

            try:
                self._git.add_worktree(worktree_path, branch_name, base_branch=base)

                info = WorktreeInfo(
                    unit_id=uid,
                    worktree_path=worktree_path,
                    branch_name=branch_name,
                )
                self._active[uid] = info
                result[uid] = info

            except GitCommandError as exc:
                logger.error("Failed to create worktree for %s: %s", uid, exc)
                raise

        logger.info(
            "Created %d worktrees for parallel batch (base: %s)",
            len(result),
            base,
        )
        return result

    async def merge_batch(
        self,
        batch_unit_ids: list[str],
        integration_branch: str,
    ) -> dict:
        """Merge all unit branches into an integration branch.

        Creates the integration branch if it doesn't exist.
        Returns {merged: [unit_ids], conflicts: [{unit_id, error}]}.
        """
        # Create integration branch from current active branch if it doesn't exist
        try:
            base = self._git.repo.active_branch.name
            self._git.create_branch(integration_branch, from_branch=base)
        except (GitCommandError, TypeError):
            pass  # branch already exists or detached HEAD

        merged = []
        conflicts = []

        for uid in batch_unit_ids:
            info = self._active.get(uid)
            if not info:
                conflicts.append({"unit_id": uid, "error": "No active worktree"})
                continue

            try:
                result = self._git.merge_branch(
                    source=info.branch_name,
                    into=integration_branch,
                )
                if result.get("success"):
                    merged.append(uid)
                else:
                    conflicts.append(
                        {
                            "unit_id": uid,
                            "error": result.get("error", "merge failed"),
                        }
                    )
            except GitCommandError as exc:
                conflicts.append({"unit_id": uid, "error": str(exc)})

        logger.info(
            "Batch merge: %d merged, %d conflicts",
            len(merged),
            len(conflicts),
        )
        return {"merged": merged, "conflicts": conflicts}

    async def cleanup_batch(self, batch_unit_ids: list[str]) -> None:
        """Remove worktrees and branches for a completed batch."""
        for uid in batch_unit_ids:
            info = self._active.pop(uid, None)
            if not info:
                continue

            try:
                self._git.remove_worktree(info.worktree_path, force=True)
            except GitCommandError as exc:
                logger.warning("Failed to remove worktree for %s: %s", uid, exc)

            try:
                self._git.repo.git.branch("-D", info.branch_name)
            except GitCommandError as exc:
                logger.warning("Failed to delete branch %s: %s", info.branch_name, exc)

    def get_worktree_path(self, unit_id: str) -> str | None:
        """Return the filesystem path for a unit's worktree, or None."""
        info = self._active.get(unit_id)
        return info.worktree_path if info else None
