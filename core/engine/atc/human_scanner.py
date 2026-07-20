# engine/atc/human_scanner.py
"""Human Developer Awareness — scan PRs and branches, register as flights.

ACE treats human code changes the same as agent changes. Active PRs and
branches are registered as flights in the ATC system so capability
locking prevents collisions between human and agent work.

Scans:
1. Open PRs via `gh pr list` (requires gh CLI)
2. Active branches via `git branch -r` (remote branches with recent commits)
3. Maps changed files → capabilities via graph realizes edges

Usage:
    scanner = HumanScanner(db_pool=pool, repo_path="/path/to/repo")
    flights = await scanner.scan(product_id="product:default")
"""

from __future__ import annotations

import json
import logging
import subprocess

from core.engine.atc.registry import FlightRegistry
from core.engine.core.db import parse_rows

logger = logging.getLogger(__name__)


class HumanScanner:
    """Scan for human developer activity and register as ATC flights."""

    def __init__(self, db_pool, repo_path: str | None = None):
        import os

        self._pool = db_pool
        self._repo_path = repo_path or os.getcwd()
        self._registry = FlightRegistry(db_pool=db_pool)

    async def scan(self, product_id: str) -> list[dict]:
        """Scan for human PRs and register new ones as flights.

        Returns list of newly registered flights.
        """
        registered = []

        # 1. Scan open PRs
        prs = self._scan_prs()
        for pr in prs:
            flight = await self._register_pr(pr, product_id)
            if flight:
                registered.append(flight)

        if registered:
            logger.info("Registered %d human flights from PRs", len(registered))

        return registered

    def _scan_prs(self) -> list[dict]:
        """Scan open PRs via gh CLI. Returns list of PR dicts."""
        try:
            result = subprocess.run(
                [
                    "gh",
                    "pr",
                    "list",
                    "--state",
                    "open",
                    "--json",
                    "number,title,headRefName,files",
                    "--limit",
                    "20",
                ],
                capture_output=True,
                text=True,
                timeout=15,
                cwd=self._repo_path,
            )

            if result.returncode != 0:
                logger.debug("gh pr list failed: %s", result.stderr)
                return []

            prs = json.loads(result.stdout)
            return prs if isinstance(prs, list) else []

        except FileNotFoundError:
            logger.debug("gh CLI not available — skipping PR scan")
            return []
        except subprocess.TimeoutExpired:
            logger.debug("gh pr list timed out")
            return []
        except Exception as exc:
            logger.debug("PR scan failed: %s", exc)
            return []

    async def _register_pr(self, pr: dict, product_id: str) -> dict | None:
        """Register a PR as a flight if not already registered."""
        pr_number = pr.get("number")
        if not pr_number:
            return None

        source_id = f"PR #{pr_number}"

        # Check if already registered
        existing = await self._registry.get_active_flights(product_id)
        for f in existing:
            if f.source == "human_pr" and f.source_id == source_id:
                return None  # already tracked

        # Map PR files → capabilities
        pr_files = [f.get("path", "") for f in pr.get("files", []) if f.get("path")]
        capabilities = await self._resolve_capabilities(pr_files, product_id)

        flight = await self._registry.register(
            product_id=product_id,
            source="human_pr",
            source_id=source_id,
            title=pr.get("title", f"PR #{pr_number}"),
            capabilities=capabilities,
            files_predicted=pr_files,
        )

        # Human PRs start as "active" (already in progress)
        try:
            await self._registry.transition(flight.id, "cleared")
            await self._registry.transition(flight.id, "active")
        except Exception:
            pass

        return {
            "flight_id": flight.id,
            "pr_number": pr_number,
            "title": pr.get("title", ""),
            "capabilities": capabilities,
            "files": pr_files,
        }

    async def _resolve_capabilities(self, file_paths: list[str], product_id: str) -> list[str]:
        """Map file paths to capability slugs via graph realizes edges."""
        if not file_paths:
            return []

        try:
            async with self._pool.connection() as db:
                result = await db.query(
                    """SELECT out.slug AS slug FROM realizes
                    WHERE in.path IN $paths
                    GROUP BY slug""",
                    {"paths": file_paths},
                )
                rows = parse_rows(result)
                return [r["slug"] for r in rows if r.get("slug")]
        except Exception:
            return []

    async def mark_pr_landed(self, pr_number: int, product_id: str) -> bool:
        """Mark a PR's flight as landed (after PR is merged).

        Called when ACE detects a PR has been merged.
        """
        source_id = f"PR #{pr_number}"
        flights = await self._registry.get_active_flights(product_id)

        for f in flights:
            if f.source == "human_pr" and f.source_id == source_id:
                try:
                    await self._registry.transition(f.id, "landing")
                    await self._registry.transition(f.id, "landed")
                    await self._registry.clear_holding_flights(f.id, product_id)
                    return True
                except Exception as exc:
                    logger.warning("Failed to land PR flight %s: %s", f.id, exc)

        return False
