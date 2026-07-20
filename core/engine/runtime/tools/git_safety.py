"""Pre-edit git safety — commit dirty state before AI edits.

Enables undo: if the AI edit is wrong, the user can git reset to
the pre-edit commit. Only activates inside a git repo.
"""

from __future__ import annotations

import logging
import subprocess

logger = logging.getLogger(__name__)

_last_safety_commit: str | None = None


def pre_edit_save(file_path: str) -> str | None:
    """If file has uncommitted changes in a git repo, stash or commit them.

    Returns the safety commit hash, or None if not in a git repo or file is clean.
    """
    global _last_safety_commit
    try:
        # Check if we're in a git repo
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None

        # Check if the specific file has changes
        result = subprocess.run(
            ["git", "diff", "--name-only", file_path],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if not result.stdout.strip():
            # Also check untracked
            result = subprocess.run(
                ["git", "ls-files", "--others", "--exclude-standard", file_path],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if not result.stdout.strip():
                return None  # file is clean

        # Stash the file's current state
        subprocess.run(["git", "add", file_path], capture_output=True, timeout=5)
        result = subprocess.run(
            ["git", "stash", "push", "-m", f"ace-pre-edit: {file_path}", "--", file_path],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            # Immediately pop it back (we just wanted the stash as a save point)
            subprocess.run(["git", "stash", "pop"], capture_output=True, timeout=5)
            _last_safety_commit = f"stash for {file_path}"
            return _last_safety_commit

        return None
    except Exception as exc:
        logger.debug("pre_edit_save failed (non-critical): %s", exc)
        return None
