# engine/sentinel/engines/github_release_watcher.py
"""S1 — GitHub Release Watcher.

Polls GitHub Releases API for all tracked competitors that have a 'github'
or 'releases' source. Fires when a new release tag is detected (stored tag
differs from latest tag). New release notes are fed through the competitive
intelligence extraction pipeline.

Runs every 12 hours (cron: 0 */12 * * *) to catch same-day releases.
"""

from __future__ import annotations

import logging

import httpx

from core.engine.core.config import settings
from core.engine.core.db import parse_rows, pool
from core.engine.sentinel.engines.competitive_observer import (
    classify_signal,
    extract_signals,
)
from core.engine.sentinel.registry import register_engine

logger = logging.getLogger(__name__)

_GITHUB_API = "https://api.github.com"
_GITHUB_REPO_RE = __import__("re").compile(r"github\.com/([A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+)")


def _github_headers() -> dict:
    token = settings.github_token
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def fetch_latest_release(owner_repo: str) -> dict | None:
    """Fetch the latest release from GitHub API.

    Returns release dict with tag_name, name, body, html_url or None on failure.
    """
    url = f"{_GITHUB_API}/repos/{owner_repo}/releases/latest"
    try:
        async with httpx.AsyncClient(timeout=15, headers=_github_headers()) as client:
            resp = await client.get(url)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        logger.warning("github_release_watcher: failed to fetch %s: %s", owner_repo, exc)
        return None


def _extract_owner_repo(sources: list[dict]) -> str | None:
    """Extract 'owner/repo' from a competitor's sources list."""
    for src in sources:
        src_type = src.get("type", "")
        url = src.get("url", "")
        if src_type in ("github", "releases") and url:
            m = _GITHUB_REPO_RE.search(url)
            if m:
                return m.group(1)
    return None


@register_engine(
    name="github_release_watcher",
    cron="0 */12 * * *",
    description="Poll GitHub Releases for tracked competitors and emit signals on new releases.",
)
async def run_github_release_watcher(product_id: str) -> dict:
    """Check GitHub releases for each tracked competitor.

    Detects new releases by comparing stored last_release_tag against the
    latest tag from the GitHub API. On a new release:
    1. Extracts competitive signals from the release notes body.
    2. Classifies each signal via the standard LLM pipeline.
    3. Writes signals to the competitive_signal table.
    4. Updates competitor.last_release_tag + last_release_checked_at.

    Returns: {competitors_checked, new_releases, signals_extracted}
    """
    results = {"competitors_checked": 0, "new_releases": 0, "signals_extracted": 0}

    async with pool.connection() as db:
        rows = parse_rows(
            await db.query(
                "SELECT id, name, tier, sources, last_release_tag FROM competitor "
                "WHERE product = <record>$product ORDER BY tier ASC",
                {"product": product_id},
            )
        )

        for comp in rows:
            owner_repo = _extract_owner_repo(comp.get("sources", []))
            if not owner_repo:
                continue

            results["competitors_checked"] += 1
            release = await fetch_latest_release(owner_repo)
            if not release:
                continue

            latest_tag = release.get("tag_name", "")
            stored_tag = comp.get("last_release_tag") or ""

            if latest_tag == stored_tag:
                # Update timestamp even if no new release (tracks last check)
                await db.query(
                    "UPDATE <record>$id SET last_release_checked_at = time::now()",
                    {"id": comp["id"]},
                )
                continue

            # New release detected
            results["new_releases"] += 1
            release_body = release.get("body", "") or ""
            release_name = release.get("name", latest_tag) or latest_tag
            content = f"## {release_name}\n\n{release_body}"

            signals = await extract_signals(content, comp["name"])
            for sig in signals:
                sig["competitor"] = comp["name"]
                sig["source_url"] = release.get("html_url", "")
                sig = await classify_signal(sig)

                await db.query(
                    """CREATE competitive_signal SET
                        competitor    = $competitor,
                        product       = <record>$product,
                        title         = $title,
                        description   = $description,
                        source_url    = $source_url,
                        relevance     = $relevance,
                        relevance_score = $relevance_score,
                        action        = $action,
                        urgency       = $urgency,
                        rationale     = $rationale,
                        signal_source = 'github_release',
                        release_tag   = $tag,
                        created_at    = time::now()
                    """,
                    {
                        "competitor": sig.get("competitor", comp["name"]),
                        "product": product_id,
                        "title": sig.get("title", ""),
                        "description": sig.get("description", ""),
                        "source_url": sig.get("source_url", ""),
                        "relevance": sig.get("relevance", "none"),
                        "relevance_score": sig.get("relevance_score", 0.5),
                        "action": sig.get("action", "monitor"),
                        "urgency": sig.get("urgency", "low"),
                        "rationale": sig.get("rationale", ""),
                        "tag": latest_tag,
                    },
                )
                results["signals_extracted"] += 1

            # Persist the new tag so we don't re-process this release
            await db.query(
                """UPDATE <record>$id SET
                    last_release_tag          = $tag,
                    last_release_checked_at   = time::now()
                """,
                {"id": comp["id"], "tag": latest_tag},
            )

    logger.info(
        "github_release_watcher: %s — %d checked, %d new releases, %d signals",
        product_id,
        results["competitors_checked"],
        results["new_releases"],
        results["signals_extracted"],
    )
    return results
