# engine/runtime/product_detector.py
"""Detect the active product from the current git repository.

Usage::

    from core.engine.runtime.product_detector import detect_product_id
    from core.engine.core.config import settings

    product_id = await detect_product_id(settings.default_org)
"""

from __future__ import annotations

import logging
import subprocess

from core.engine.core.db import parse_rows, pool

logger = logging.getLogger(__name__)


def _get_git_root() -> str | None:
    """Return the absolute path of the current git root, or None."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


async def detect_product_id(default: str) -> str:
    """Detect product_id from the current git root.

    Queries project.repo_path → project.product.
    Returns *default* if not in a git repo, no match found, or DB unavailable.
    """
    git_root = _get_git_root()
    if not git_root:
        return default

    try:
        await pool.init()  # idempotent — safe to call if already initialized
        async with pool.connection() as db:
            result = await db.query(
                "SELECT product FROM project WHERE repo_path = $repo_path LIMIT 1",
                {"repo_path": git_root},
            )
            rows = parse_rows(result)
            if rows and rows[0].get("product"):
                product_id = str(rows[0]["product"])
                logger.debug("Product auto-detected: %s (from %s)", product_id, git_root)
                return product_id
    except Exception as exc:
        logger.debug("Product detection DB query failed: %s", exc)

    return default
