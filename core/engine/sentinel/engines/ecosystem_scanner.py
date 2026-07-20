"""Sentinel engine: Ecosystem Scanner — discover relevant open-source projects.

Scans GitHub and web for tools/libraries relevant to ACE's specialties and
workspaces. Queues discoveries for gap_researcher to synthesize into insights.

Spec: docs/superpowers/specs/2026-03-25-ecosystem-scanner-design.md
"""

from __future__ import annotations

import logging
import re
from typing import Any

from core.engine.core.config import settings
from core.engine.core.db import pool
from core.engine.core.exceptions import ValidationError
from core.engine.core.llm import llm
from core.engine.core.search import github_search, web_search
from core.engine.sentinel.engines import queue_research
from core.engine.sentinel.registry import register_engine

logger = logging.getLogger(__name__)

SOURCE_DOMAIN = "sentinel.ecosystem-scanner"

RELEVANCE_THRESHOLD = 0.6
HIGH_RELEVANCE_THRESHOLD = 0.8

SPECIALTY_QUERY_PROMPT = """Given this specialty "{slug}" ({perspective}) in discipline "{discipline}":
Description: {description}
Key insights: {insights}

Generate 3-5 GitHub/web search queries to discover open-source projects,
libraries, or frameworks that could strengthen this specialty's capabilities.

Focus on:
- Tools that solve problems these insights describe
- Alternatives or complements to known tools in this space
- Emerging projects in this space (2025-2026)
- {perspective}-relevant resources (e.g., research papers/implementations
  for theorists, production-ready libraries for practitioners)

Return JSON array: ["query1", "query2", ...]"""

RELEVANCE_PROMPT = """Score each project's relevance to our {context_type} (0.0-1.0).

Projects:
{numbered_list}

Our context: {context}

Return JSON array (same order as input):
[
  {{"relevance": 0.0-1.0, "reason": "...", "integration_angle": "..."}},
  ...
]"""


def _extract_url(text: str) -> str | None:
    """Extract first HTTP(S) URL from a string."""
    match = re.search(r"https?://\S+", text)
    return match.group(0).rstrip(")>,") if match else None


async def _build_seen_urls(db: Any, product_id: str) -> set[str]:
    """Build set of already-seen URLs from research_queue + experiment_log."""
    rq_result = await db.query(
        """
        SELECT context FROM research_queue
        WHERE product = <record>$product AND source = 'ecosystem-scanner'
        """,
        {"product": product_id},
    )
    rq_rows = rq_result[0] if rq_result and isinstance(rq_result[0], list) else (rq_result or [])

    el_result = await db.query(
        """
        SELECT details.finding_url AS url FROM experiment_log
        WHERE product = <record>$product AND details.finding_url IS NOT NONE
        """,
        {"product": product_id},
    )
    el_rows = el_result[0] if el_result and isinstance(el_result[0], list) else (el_result or [])

    seen: set[str] = set()
    for row in rq_rows:
        if not isinstance(row, dict):
            continue
        for line in row.get("context", "").split("\n"):
            if "http" in line:
                url = _extract_url(line)
                if url:
                    seen.add(url)
    for row in el_rows:
        if not isinstance(row, dict):
            continue
        url = row.get("url", "")
        if url:
            seen.add(url)

    return seen


async def _scan_specialties(
    db: Any,
    llm_provider: Any,
    product_id: str,
    seen_urls: set[str],
    *,
    github_search_fn=None,
    web_search_fn=None,
) -> dict:
    """Mode 1: Scan for tools relevant to active specialties."""
    gh_search = github_search_fn or github_search
    w_search = web_search_fn or web_search

    # Query specialty table directly — it tracks task_count
    result = await db.query(
        """
        SELECT id, slug, description, perspective, task_count,
               discipline.slug AS discipline_slug
        FROM specialty
        WHERE product = <record>$product AND task_count >= 10
        ORDER BY task_count DESC
        """,
        {"product": product_id},
    )
    active = result[0] if result and isinstance(result[0], list) else (result or [])

    stats = {
        "specialties_scanned": 0,
        "disciplines_covered": [],
        "github_results": 0,
        "web_results": 0,
        "relevant_findings": 0,
        "queued": 0,
        "deduped": 0,
        "llm_calls": 0,
        "to_queue": [],
    }

    for row in active:
        if not isinstance(row, dict):
            continue

        slug = row.get("slug", "")
        description = row.get("description", "")
        perspective = row.get("perspective", "practitioner")
        discipline_slug = row.get("discipline_slug", "") or ""
        spec_id = row.get("id", "")

        # Load top insights
        insight_result = await db.query(
            """
            SELECT content, confidence FROM insight
            WHERE specialty = $spec_id AND status = 'active'
            ORDER BY confidence DESC
            LIMIT 5
            """,
            {"spec_id": spec_id},
        )
        insight_rows = (
            insight_result[0] if insight_result and isinstance(insight_result[0], list) else (insight_result or [])
        )
        insights_text = "\n".join(r.get("content", "") for r in insight_rows if isinstance(r, dict))

        # LLM call 1: generate queries
        queries = await llm_provider.complete_json(
            SPECIALTY_QUERY_PROMPT.format(
                slug=slug,
                perspective=perspective,
                discipline=discipline_slug,
                description=description,
                insights=insights_text or "(no insights yet)",
            ),
            model=settings.llm_budget_model,
        )
        stats["llm_calls"] += 1

        if not isinstance(queries, list):
            queries = []

        # Execute searches
        all_findings = []
        for q in queries[:5]:
            gh_results = await gh_search(q, max_results=5, min_stars=50)
            w_results = await w_search(q, max_results=3)
            stats["github_results"] += len(gh_results)
            stats["web_results"] += len(w_results)
            for r in gh_results:
                all_findings.append(r)
            for r in w_results:
                all_findings.append(
                    {
                        "name": r.get("title", ""),
                        "url": r.get("url", ""),
                        "description": r.get("snippet", ""),
                        "stars": "N/A",
                        "updated_at": "N/A",
                        "topics": [],
                        "language": "",
                    }
                )

        # Dedup against seen
        unique_findings = []
        for f in all_findings:
            url = f.get("url", "")
            if url and url not in seen_urls:
                unique_findings.append(f)
                seen_urls.add(url)
            else:
                stats["deduped"] += 1

        if not unique_findings:
            stats["specialties_scanned"] += 1
            if discipline_slug and discipline_slug not in stats["disciplines_covered"]:
                stats["disciplines_covered"].append(discipline_slug)
            continue

        # LLM call 2: batch relevance scoring
        numbered = "\n".join(
            f"{i + 1}. {f['name']}: {f.get('description', '')[:200]} (stars: {f.get('stars', 'N/A')})"
            for i, f in enumerate(unique_findings)
        )
        context = f"Specialty: {slug} ({perspective}), Discipline: {discipline_slug}, Description: {description}"

        scores = await llm_provider.complete_json(
            RELEVANCE_PROMPT.format(
                context_type=f"specialty '{slug}'",
                numbered_list=numbered,
                context=context,
            ),
            model=settings.llm_budget_model,
        )
        stats["llm_calls"] += 1

        if not isinstance(scores, list):
            scores = []

        for i, score in enumerate(scores):
            if i >= len(unique_findings):
                break
            if not isinstance(score, dict):
                continue
            relevance = score.get("relevance", 0)
            if relevance >= RELEVANCE_THRESHOLD:
                stats["relevant_findings"] += 1
                stats["to_queue"].append(
                    {
                        "finding": unique_findings[i],
                        "score": score,
                        "specialty_slug": slug,
                        "discipline_slug": discipline_slug,
                        "scan_target": f"specialty:{slug}",
                    }
                )

        stats["specialties_scanned"] += 1
        if discipline_slug and discipline_slug not in stats["disciplines_covered"]:
            stats["disciplines_covered"].append(discipline_slug)

    return stats


WORKSPACE_QUERY_PROMPT = """This workspace "{name}" has:
Active specialties: {specialties}
Tools: {tools}
Vocabulary: {vocabulary}
Org domains: {active_domains}

Generate 3-5 search queries to discover open-source projects that solve
architectural problems this workspace faces. Think about:
- Infrastructure patterns (knowledge graphs, memory systems, experimentation)
- Integration opportunities (MCP servers, SDKs, agent frameworks)
- Research implementations relevant to this workspace's specialties

Return JSON array: ["query1", "query2", ...]"""


async def _scan_workspaces(
    db: Any,
    llm_provider: Any,
    product_id: str,
    seen_urls: set[str],
    *,
    github_search_fn=None,
    web_search_fn=None,
) -> dict:
    """Mode 2: Scan for projects relevant to workspace architecture."""
    gh_search = github_search_fn or github_search
    w_search = web_search_fn or web_search

    ws_result = await db.query(
        """
        SELECT name, active_domains, tools, vocabulary
        FROM workspace
        WHERE product = <record>$product
        """,
        {"product": product_id},
    )
    workspaces = ws_result[0] if ws_result and isinstance(ws_result[0], list) else (ws_result or [])

    # Load active specialties for context
    spec_result = await db.query(
        """
        SELECT slug, description, perspective, discipline.slug AS discipline, task_count
        FROM specialty
        WHERE product = <record>$product AND bootstrapped = true
        ORDER BY task_count DESC
        LIMIT 10
        """,
        {"product": product_id},
    )
    spec_rows = spec_result[0] if spec_result and isinstance(spec_result[0], list) else (spec_result or [])
    specialties_text = (
        ", ".join(f"{r.get('slug', '')} ({r.get('perspective', '')})" for r in spec_rows if isinstance(r, dict))
        or "(none)"
    )

    stats = {
        "workspaces_scanned": 0,
        "github_results": 0,
        "web_results": 0,
        "relevant_findings": 0,
        "queued": 0,
        "deduped": 0,
        "llm_calls": 0,
        "to_queue": [],
    }

    # Best-fit specialty for workspace findings
    best_specialty = spec_rows[0].get("slug", "") if spec_rows else ""
    best_discipline = ""
    if spec_rows:
        d = spec_rows[0].get("discipline", "")
        best_discipline = d if isinstance(d, str) else (d.get("slug", "") if isinstance(d, dict) else "")

    for ws in workspaces:
        if not isinstance(ws, dict):
            continue

        ws_name = ws.get("name", "")
        tools = ws.get("tools", [])
        vocabulary = ws.get("vocabulary", {})
        active_domains = ws.get("active_domains", [])

        # LLM call 1: generate queries
        queries = await llm_provider.complete_json(
            WORKSPACE_QUERY_PROMPT.format(
                name=ws_name,
                specialties=specialties_text,
                tools=", ".join(tools) if isinstance(tools, list) else str(tools),
                vocabulary=str(vocabulary)[:500],
                active_domains=", ".join(active_domains) if isinstance(active_domains, list) else str(active_domains),
            ),
            model=settings.llm_budget_model,
        )
        stats["llm_calls"] += 1

        if not isinstance(queries, list):
            queries = []

        # Execute searches
        all_findings = []
        for q in queries[:5]:
            gh_results = await gh_search(q, max_results=5, min_stars=50)
            w_results = await w_search(q, max_results=3)
            stats["github_results"] += len(gh_results)
            stats["web_results"] += len(w_results)
            for r in gh_results:
                all_findings.append(r)
            for r in w_results:
                all_findings.append(
                    {
                        "name": r.get("title", ""),
                        "url": r.get("url", ""),
                        "description": r.get("snippet", ""),
                        "stars": "N/A",
                        "updated_at": "N/A",
                        "topics": [],
                        "language": "",
                    }
                )

        # Dedup
        unique_findings = []
        for f in all_findings:
            url = f.get("url", "")
            if url and url not in seen_urls:
                unique_findings.append(f)
                seen_urls.add(url)
            else:
                stats["deduped"] += 1

        if not unique_findings:
            stats["workspaces_scanned"] += 1
            continue

        # LLM call 2: batch relevance scoring
        numbered = "\n".join(
            f"{i + 1}. {f['name']}: {f.get('description', '')[:200]} (stars: {f.get('stars', 'N/A')})"
            for i, f in enumerate(unique_findings)
        )
        context = f"Workspace: {ws_name}, Tools: {', '.join(tools) if isinstance(tools, list) else tools}, Specialties: {specialties_text}"

        scores = await llm_provider.complete_json(
            RELEVANCE_PROMPT.format(
                context_type=f"workspace '{ws_name}'",
                numbered_list=numbered,
                context=context,
            ),
            model=settings.llm_budget_model,
        )
        stats["llm_calls"] += 1

        if not isinstance(scores, list):
            scores = []

        for i, score in enumerate(scores):
            if i >= len(unique_findings):
                break
            if not isinstance(score, dict):
                continue
            relevance = score.get("relevance", 0)
            if relevance >= RELEVANCE_THRESHOLD:
                stats["relevant_findings"] += 1
                stats["to_queue"].append(
                    {
                        "finding": unique_findings[i],
                        "score": score,
                        "specialty_slug": best_specialty,
                        "discipline_slug": best_discipline,
                        "scan_target": f"workspace:{ws_name}",
                    }
                )

        stats["workspaces_scanned"] += 1

    return stats


def _validate_ecosystem_scanner_inputs(product_id: str, budget: int = 100) -> None:
    """Validate ecosystem scanner inputs before querying the database.

    Raises ValidationError for malformed product_id or out-of-range budget
    so the engine fails fast with a clear error rather than running LLM
    calls against invalid data.
    """
    if not product_id or ":" not in product_id:
        raise ValidationError(f"Invalid product_id for ecosystem-scanner: {product_id!r}")
    if not (0 <= budget <= 500):
        raise ValidationError(f"budget must be in [0, 500], got {budget}")


@register_engine(
    name="ecosystem_scanner",
    cron="0 3 * * tue",  # 3 AM Tuesdays
    description="Weekly ecosystem scan — discover relevant tools, libraries, and projects",
)
async def run_ecosystem_scanner(product_id: str) -> dict:
    """Discover relevant open-source projects for org's specialties and workspaces."""
    _validate_ecosystem_scanner_inputs(product_id)
    async with pool.connection() as db:
        seen_urls = await _build_seen_urls(db, product_id)

        # Mode 1: Specialty tooling scan
        spec_stats = await _scan_specialties(
            db,
            llm,
            product_id,
            seen_urls,
            github_search_fn=github_search,
            web_search_fn=web_search,
        )

        # Mode 2: Workspace architecture scan
        ws_stats = await _scan_workspaces(
            db,
            llm,
            product_id,
            seen_urls,
            github_search_fn=github_search,
            web_search_fn=web_search,
        )

        # Queue all findings
        all_to_queue = spec_stats.pop("to_queue", []) + ws_stats.pop("to_queue", [])
        queued = 0
        for item in all_to_queue:
            finding = item["finding"]
            score = item["score"]
            specialty_slug = item.get("specialty_slug", "")
            discipline_slug = item.get("discipline_slug", "")
            scan_target = item.get("scan_target", "")

            await queue_research(
                db,
                product_id=product_id,
                query=f"Evaluate {finding['name']} for {scan_target}",
                context=(
                    f"[ecosystem-discovery] {finding['name']} ({finding['url']})\n"
                    f"Stars: {finding.get('stars', 'N/A')} | "
                    f"Updated: {finding.get('updated_at', 'N/A')}\n"
                    f"Target specialty: {specialty_slug or 'N/A'} | "
                    f"Discipline: {discipline_slug or 'N/A'}\n"
                    f"Relevance: {score['relevance']}\n"
                    f"Reason: {score['reason']}\n"
                    f"Integration angle: {score['integration_angle']}"
                ),
                priority="high" if score["relevance"] >= HIGH_RELEVANCE_THRESHOLD else "medium",
                source="ecosystem-scanner",
            )
            queued += 1

        total_llm = spec_stats["llm_calls"] + ws_stats["llm_calls"]

        logger.info(
            "Ecosystem scan complete: %d specialties, %d workspaces, %d queued, %d LLM calls",
            spec_stats["specialties_scanned"],
            ws_stats["workspaces_scanned"],
            queued,
            total_llm,
        )

        return {
            "specialties_scanned": spec_stats["specialties_scanned"],
            "workspaces_scanned": ws_stats["workspaces_scanned"],
            "disciplines_covered": spec_stats.get("disciplines_covered", []),
            "github_results": spec_stats["github_results"] + ws_stats["github_results"],
            "web_results": spec_stats["web_results"] + ws_stats["web_results"],
            "relevant_findings": spec_stats["relevant_findings"] + ws_stats["relevant_findings"],
            "queued": queued,
            "deduped": spec_stats["deduped"] + ws_stats["deduped"],
            "llm_calls": total_llm,
        }
