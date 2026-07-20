# engine/scanner/external.py
"""External repository scanner — clone and deep-scan competitor/reference repos.

Accepts a GitHub URL ("https://github.com/owner/repo") or a short slug
("owner/repo"). Clones to a persistent local directory, runs the full
AST+git scanner, and upserts a competitor record in the DB.
"""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

import httpx
from surrealdb import RecordID

from core.engine.core.config import settings
from core.engine.core.db import pool
from core.engine.scanner.scanner import scan_repo

logger = logging.getLogger(__name__)

_GH_URL_RE = re.compile(r"(?:https?://github\.com/)?([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$")
_GH_API = "https://api.github.com"

DEFAULT_CLONE_BASE = Path.home() / "Projects" / "competitor_repos"


def parse_github_url(url_or_slug: str) -> tuple[str, str]:
    """Parse a GitHub URL or 'owner/repo' slug to (owner, repo).

    Raises ValueError if the input cannot be parsed.
    """
    match = _GH_URL_RE.match(url_or_slug.strip())
    if not match:
        raise ValueError(f"Cannot parse GitHub URL/slug: {url_or_slug!r}")
    return match.group(1), match.group(2)


async def _fetch_github_metadata(owner: str, repo: str, token: str = "") -> dict:
    """Fetch repo metadata from GitHub REST API.

    Works without a token for public repos but may hit rate limits quickly.
    """
    headers: dict[str, str] = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async with httpx.AsyncClient(timeout=15.0) as http:
        try:
            resp = await http.get(f"{_GH_API}/repos/{owner}/{repo}", headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return {
                "stars": data.get("stargazers_count", 0),
                "language": data.get("language") or "",
                "description": data.get("description") or "",
                "topics": data.get("topics", []),
                "forks": data.get("forks_count", 0),
                "open_issues": data.get("open_issues_count", 0),
                "default_branch": data.get("default_branch", "main"),
                "clone_url": data.get("clone_url") or f"https://github.com/{owner}/{repo}.git",
                "pushed_at": data.get("pushed_at"),
                "homepage": data.get("homepage") or "",
                "license": (data.get("license") or {}).get("spdx_id") or "",
            }
        except Exception as exc:
            logger.warning("GitHub metadata fetch failed for %s/%s: %s", owner, repo, exc)
            return {
                "stars": 0,
                "language": "",
                "description": "",
                "topics": [],
                "forks": 0,
                "open_issues": 0,
                "default_branch": "main",
                "clone_url": f"https://github.com/{owner}/{repo}.git",
                "pushed_at": None,
                "homepage": "",
                "license": "",
            }


def _clone_or_pull(clone_url: str, local_path: Path) -> None:
    """Git clone if not present, git pull if it is. Uses --depth=500 for speed."""
    if (local_path / ".git").exists():
        logger.info("Pulling latest changes in %s", local_path)
        result = subprocess.run(
            ["git", "pull", "--ff-only"],
            cwd=str(local_path),
            capture_output=True,
            timeout=120,
        )
        if result.returncode != 0:
            logger.warning(
                "git pull failed (non-fatal, using existing clone): %s",
                result.stderr.decode()[:200],
            )
    else:
        logger.info("Cloning %s → %s", clone_url, local_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", "--depth=500", clone_url, str(local_path)],
            check=True,
            capture_output=True,
            timeout=300,
        )


async def scan_external_repo(
    github_url: str,
    product_id: str = "product:platform",
    clone_base: str | None = None,
    tier: int = 2,
) -> dict:
    """Clone and deep-scan an external GitHub repo.

    Steps:
      1. Parse owner/repo from URL or slug
      2. Fetch GitHub metadata (stars, language, topics, …)
      3. git clone or git pull to a persistent local directory
      4. Run full scan_repo() — AST + git history → graph_file, graph_function,
         graph_decision, imports edges, co-change edges
      5. Upsert competitor record in DB

    Args:
        github_url:  Full URL or 'owner/repo' slug
        product_id:  ACE product to associate with (default: product:platform)
        clone_base:  Override clone directory (default: ~/Projects/competitor_repos/)
        tier:        1=direct competitor, 2=adjacent, 3=inspirational

    Returns:
        {graph_id, competitor_id, local_path, stats, metadata}
    """
    owner, repo = parse_github_url(github_url)

    # Build stable, collision-free identifiers
    slug = f"{owner}_{repo}".lower().replace("-", "_").replace(".", "_")
    graph_id = f"competitor_{slug}"
    competitor_rid = RecordID("competitor", slug)

    token = settings.github_token
    metadata = await _fetch_github_metadata(owner, repo, token)

    base = Path(clone_base) if clone_base else DEFAULT_CLONE_BASE
    local_path = base / f"{owner}_{repo}"

    _clone_or_pull(metadata["clone_url"], local_path)

    source_url = f"https://github.com/{owner}/{repo}"

    logger.info(
        "Scanning external repo %s/%s at %s (graph_id=%s)",
        owner,
        repo,
        local_path,
        graph_id,
    )
    stats = await scan_repo(str(local_path), graph_id=graph_id)

    # Upsert competitor record — slug-based RecordID makes UPSERT idempotent
    async with pool.connection() as db:
        await db.query(
            """
            UPSERT $id SET
                name         = $name,
                tier         = $tier,
                sources      = [{"type": "github", "url": $url}],
                domains      = $topics,
                product      = <record>$product,
                graph_id     = $gid,
                last_scanned = time::now()
            """,
            {
                "id": competitor_rid,
                "name": f"{owner}/{repo}",
                "tier": tier,
                "url": source_url,
                "topics": metadata.get("topics", []),
                "product": product_id,
                "gid": graph_id,
            },
        )

    # Bootstrap capability map from the scanned graph so competitive intelligence
    # tools can answer "what does this repo actually do?" with code evidence.
    # proposals are auto-committed as 'planned' capabilities on this competitor.
    capabilities_mapped = 0
    try:
        from core.engine.product.capability_mapper import CapabilityMapper

        mapper = CapabilityMapper(pool)
        # Pass graph_id explicitly so bootstrap_from_graph skips the product→graph
        # lookup and queries files directly by the competitor's graph_id.
        proposals = await mapper.bootstrap_from_graph(product_id, graph_id=graph_id)

        async with pool.connection() as db:
            for cap in proposals:
                cap_slug = cap.get("slug", "")
                if not cap_slug:
                    continue
                await db.query(
                    """
                    UPSERT capability SET
                        product      = <record>$product,
                        name         = $name,
                        slug         = <string>$slug,
                        description  = $description,
                        file_glob    = $glob,
                        graph_id     = $gid,
                        status       = 'planned',
                        tags         = ['external', 'auto-mapped'],
                        updated_at   = time::now()
                    WHERE product = <record>$product AND slug = <string>$slug
                    """,
                    {
                        "product": competitor_rid,  # scope to this competitor, not the platform
                        "name": cap.get("name", cap_slug),
                        "slug": f"{slug}__{cap_slug}",
                        "description": cap.get("description", ""),
                        "glob": cap.get("file_glob", ""),
                        "gid": graph_id,
                    },
                )
                capabilities_mapped += 1
        logger.info("Capability bootstrap for %s/%s: %d capabilities", owner, repo, capabilities_mapped)
    except Exception as exc:
        logger.warning("Capability bootstrap failed for %s/%s (non-fatal): %s", owner, repo, exc)

    # Extract competitive signals from README + repo description
    signals_written = await _extract_and_store_signals(
        owner=owner,
        repo=repo,
        metadata=metadata,
        product_id=product_id,
        token=token,
    )

    logger.info(
        "External scan complete: competitor=%s graph=%s files=%d decisions=%d capabilities=%d signals=%d",
        f"{owner}/{repo}",
        graph_id,
        stats.get("files_created", 0),
        stats.get("decisions_created", 0),
        capabilities_mapped,
        signals_written,
    )

    return {
        "graph_id": graph_id,
        "competitor_id": str(competitor_rid),
        "local_path": str(local_path),
        "stats": stats,
        "capabilities_mapped": capabilities_mapped,
        "signals_written": signals_written,
        "metadata": {
            "owner": owner,
            "repo": repo,
            "stars": metadata["stars"],
            "language": metadata["language"],
            "description": metadata["description"],
            "topics": metadata["topics"],
            "forks": metadata["forks"],
        },
    }


async def _fetch_readme(owner: str, repo: str, token: str = "") -> str:
    """Fetch README content from GitHub API. Returns plain text, empty on failure."""
    headers: dict[str, str] = {
        "Accept": "application/vnd.github.raw+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async with httpx.AsyncClient(timeout=15.0) as http:
        try:
            resp = await http.get(f"{_GH_API}/repos/{owner}/{repo}/readme", headers=headers)
            resp.raise_for_status()
            return resp.text[:15000]  # cap to avoid oversized LLM prompts
        except Exception as exc:
            logger.debug("README fetch failed for %s/%s: %s", owner, repo, exc)
            return ""


async def _extract_and_store_signals(
    owner: str,
    repo: str,
    metadata: dict,
    product_id: str,
    token: str = "",
) -> int:
    """Fetch README, extract competitive signals, write to competitive_signal table.

    Reuses extract_signals() + classify_signal() from competitive_observer so the
    same LLM prompts and classification logic apply regardless of trigger source.
    Returns count of signals written.
    """
    from core.engine.sentinel.engines.competitive_observer import classify_signal, extract_signals

    comp_name = f"{owner}/{repo}"
    source_url = f"https://github.com/{owner}/{repo}"

    # Build content: description + README
    parts: list[str] = []
    if metadata.get("description"):
        parts.append(f"Description: {metadata['description']}")
    if metadata.get("topics"):
        parts.append(f"Topics: {', '.join(metadata['topics'])}")
    readme = await _fetch_readme(owner, repo, token)
    if readme:
        parts.append(f"\n\n{readme}")

    content = "\n".join(parts)
    if not content.strip():
        return 0

    signals = await extract_signals(content, comp_name)
    if not signals:
        return 0

    written = 0
    async with pool.connection() as db:
        for sig in signals:
            sig["competitor"] = comp_name
            sig["source_url"] = source_url
            sig = await classify_signal(sig)

            try:
                await db.query(
                    """
                    CREATE competitive_signal SET
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
                        created_at    = time::now()
                    """,
                    {
                        "competitor": comp_name,
                        "product": product_id,
                        "title": sig.get("title", ""),
                        "description": sig.get("description", ""),
                        "source_url": source_url,
                        "relevance": sig.get("relevance", "none"),
                        "relevance_score": float(sig.get("relevance_score", 0.5)),
                        "action": sig.get("action", "monitor"),
                        "urgency": sig.get("urgency", "low"),
                        "rationale": sig.get("rationale", ""),
                    },
                )
                written += 1
            except Exception as exc:
                logger.warning("Failed to write competitive_signal for %s: %s", comp_name, exc)

    return written
