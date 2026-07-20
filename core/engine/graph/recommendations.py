# engine/graph/recommendations.py
"""Recommendation engine — analyzes the code graph and produces actionable project recommendations.

Runs several analyzers against the graph and optionally calls the budget LLM
for deeper insights.  Results are cached for 1 hour to avoid regenerating on
every page load.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from typing import Literal

from core.engine.core.config import settings
from core.engine.core.db import parse_one, parse_rows, pool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

RecType = Literal["risk", "improvement", "suggestion", "competitive", "task"]
Severity = Literal["high", "medium", "low"]
Action = Literal["fix", "review", "explore", "dismiss"]
Source = Literal["graph_analysis", "overnight", "competitive", "self_optimizer"]


def _rec_id(seed: str) -> str:
    """Deterministic recommendation ID from a seed string."""
    return "rec_" + hashlib.md5(seed.encode()).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

_cache: dict[str, tuple[float, list[dict]]] = {}
_CACHE_TTL = 3600  # 1 hour


def _validate_graph_input(graph_id: str, limit: int | None = None) -> None:
    """Validate graph_id format and optional limit before DB queries.

    Prevents empty graph_id from matching every graph row and clamps limit to
    avoid runaway result sets on large graphs.
    """
    if not graph_id or not graph_id.strip():
        raise ValueError(f"graph_id must be non-empty, got {graph_id!r}")
    if limit is not None and not (1 <= limit <= 100):
        raise ValueError(f"limit must be in [1, 100], got {limit}")


def _get_cached(graph_id: str) -> list[dict] | None:
    entry = _cache.get(graph_id)
    if entry and (time.time() - entry[0]) < _CACHE_TTL:
        return entry[1]
    return None


def _set_cached(graph_id: str, recs: list[dict]) -> None:
    _cache[graph_id] = (time.time(), recs)


def clear_cache(graph_id: str | None = None) -> None:
    """Clear recommendation cache (for testing or after a scan)."""
    if graph_id:
        _cache.pop(graph_id, None)
    else:
        _cache.clear()


# ---------------------------------------------------------------------------
# Dismissed recommendations (in-memory for now; could persist to DB)
# ---------------------------------------------------------------------------

_dismissed: set[str] = set()


def dismiss(rec_id: str) -> None:
    _dismissed.add(rec_id)


def is_dismissed(rec_id: str) -> bool:
    return rec_id in _dismissed


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def generate_recommendations(
    graph_id: str = "default",
    limit: int = 8,
) -> list[dict]:
    """Analyze the code graph and generate actionable recommendations.

    Returns a list of recommendation dicts.  Cached for 1 hour.
    """
    _validate_graph_input(graph_id, limit)
    cached = _get_cached(graph_id)
    if cached is not None:
        return [r for r in cached if not is_dismissed(r["id"])][:limit]

    recs: list[dict] = []

    try:
        # Run analyzers concurrently — each appends to a shared list
        results = await asyncio.gather(
            _analyze_fragile_code(graph_id),
            _analyze_code_quality(graph_id),
            _analyze_stale_decisions(graph_id),
            _analyze_self_optimizer_proposals(graph_id),
            return_exceptions=True,
        )

        for result in results:
            if isinstance(result, Exception):
                logger.warning("Analyzer failed: %s", result)
                continue
            recs.extend(result)

        # Run LLM-powered deep analysis last (depends on knowing which files
        # are already flagged so it can add novel insights)
        try:
            llm_recs = await _analyze_with_llm(graph_id, existing_recs=recs)
            recs.extend(llm_recs)
        except Exception as exc:
            logger.warning("LLM analysis failed: %s", exc)

    except Exception as exc:
        logger.error("Recommendation generation failed: %s", exc)

    # Deduplicate by id and limit
    seen: set[str] = set()
    unique: list[dict] = []
    for r in recs:
        if r["id"] not in seen and not is_dismissed(r["id"]):
            seen.add(r["id"])
            unique.append(r)
    unique = unique[:limit]

    _set_cached(graph_id, unique)
    return unique


# ---------------------------------------------------------------------------
# Analyzer 1: Fragile Code Detection
# ---------------------------------------------------------------------------


async def _analyze_fragile_code(graph_id: str) -> list[dict]:
    """Find files with high change frequency AND many dependents."""
    recs: list[dict] = []

    async with pool.connection() as db:
        result = await db.query(
            """
            SELECT path, change_frequency, name
            FROM graph_file
            WHERE graph_id = $gid AND change_frequency > 3
            ORDER BY change_frequency DESC
            LIMIT 5
            """,
            {"gid": graph_id},
        )
        files = parse_rows(result)

        for f in files:
            path = f.get("path", "")
            name = f.get("name", path.split("/")[-1] if path else "unknown")
            change_freq = f.get("change_frequency", 0)

            # Count dependents (files that import this one)
            file_slug = path.replace("/", "_").replace(".", "_")
            dep_result = await db.query(
                f"SELECT count() AS cnt FROM imports WHERE out = graph_file:{file_slug} GROUP ALL",
            )
            dep_row = parse_one(dep_result)
            dependents = dep_row.get("cnt", 0) if dep_row else 0

            if change_freq > 5 and dependents > 15:
                severity = "high"
            elif change_freq > 3 and dependents > 5:
                severity = "medium"
            elif change_freq > 5:
                severity = "medium"
            else:
                continue

            rec_id = _rec_id(f"fragile:{path}")
            recs.append(
                {
                    "id": rec_id,
                    "type": "risk",
                    "title": f"{name} is a high-churn dependency",
                    "description": (
                        f"Changed {change_freq} times with {dependents} files depending on it. "
                        f"Bugs here cascade widely."
                    ),
                    "action": "review",
                    "action_prompt": (
                        f"Review {path} for stability improvements. "
                        f"This file has {change_freq} changes and {dependents} dependents. "
                        f"Identify fragile patterns, missing error handling, or overly broad interfaces "
                        f"that could be narrowed. Suggest concrete refactoring steps."
                    ),
                    "severity": severity,
                    "source": "graph_analysis",
                    "related_files": [path],
                    "_change_freq": change_freq,
                    "_dependents": dependents,
                }
            )

    # Ask LLM for specific improvement for the top fragile file
    if recs:
        top = recs[0]
        try:
            llm_rec = await _llm_fragile_insight(graph_id, top)
            if llm_rec:
                recs[0] = {**recs[0], **llm_rec}
        except Exception as exc:
            logger.debug("LLM fragile insight failed: %s", exc)

    return recs


async def _llm_fragile_insight(graph_id: str, rec: dict) -> dict | None:
    """Ask the budget LLM for a specific improvement suggestion for a fragile file."""
    from core.engine.core.llm import llm

    path = rec["related_files"][0] if rec.get("related_files") else "unknown"
    change_freq = rec.get("_change_freq", 0)
    dependents = rec.get("_dependents", 0)

    # Get function list for this file
    async with pool.connection() as db:
        func_result = await db.query(
            """
            SELECT name FROM graph_function
            WHERE graph_id = $gid AND file_path = $path
            ORDER BY name
            LIMIT 30
            """,
            {"gid": graph_id, "path": path},
        )
        functions = [r.get("name", "") for r in parse_rows(func_result)]

    if not functions:
        return None

    prompt = (
        f"This file has been changed {change_freq} times and {dependents} files depend on it.\n"
        f"File: {path}\n"
        f"Functions: {', '.join(functions)}\n\n"
        f"Suggest ONE specific improvement to reduce risk. Be concrete — name the function or pattern.\n"
        f'Return JSON: {{"title": "...", "description": "...", "action_prompt": "..."}}'
    )

    try:
        data = await llm.complete_json(prompt, model=settings.llm_budget_model)
        return {
            "title": data.get("title", rec["title"]),
            "description": data.get("description", rec["description"]),
            "action_prompt": data.get("action_prompt", rec["action_prompt"]),
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Analyzer 2: Code Quality Patterns (pure graph queries — no LLM)
# ---------------------------------------------------------------------------


async def _analyze_code_quality(graph_id: str) -> list[dict]:
    """Look for structural patterns in the graph that suggest improvements."""
    recs: list[dict] = []

    async with pool.connection() as db:
        # --- Large modules (>20 functions) ---
        # SurrealDB v3 does not support HAVING — wrap the GROUP BY result in
        # an outer SELECT and filter on the aggregate column there. The prior
        # query parsed with "Unexpected token `an identifier`, expected Eof"
        # at the HAVING keyword on every analyzer run.
        large_result = await db.query(
            """
            SELECT * FROM (
                SELECT file_path, count() AS func_count
                FROM graph_function
                WHERE graph_id = $gid
                GROUP BY file_path
            )
            WHERE func_count > 20
            ORDER BY func_count DESC
            LIMIT 3
            """,
            {"gid": graph_id},
        )
        for row in parse_rows(large_result):
            path = row.get("file_path", "")
            count = row.get("func_count", 0)
            name = path.split("/")[-1] if path else "unknown"
            recs.append(
                {
                    "id": _rec_id(f"large_module:{path}"),
                    "type": "improvement",
                    "title": f"Consider splitting {name}",
                    "description": (
                        f"This file has {count} functions. Large modules are harder to test "
                        f"and reason about. Splitting into focused sub-modules improves maintainability."
                    ),
                    "action": "review",
                    "action_prompt": (
                        f"Analyze {path} which has {count} functions. "
                        f"Identify logical groupings and suggest how to split it into "
                        f"smaller, focused modules. Preserve the public API."
                    ),
                    "severity": "medium",
                    "source": "graph_analysis",
                    "related_files": [path],
                }
            )

        # --- Circular dependencies (A imports B, B imports A) ---
        cycle_result = await db.query(
            """
            SELECT in.path AS from_path, out.path AS to_path
            FROM imports
            WHERE in.graph_id = $gid
              AND (SELECT count() FROM imports WHERE in = $parent.out AND out = $parent.in) > 0
            LIMIT 5
            """,
            {"gid": graph_id},
        )
        seen_cycles: set[str] = set()
        for row in parse_rows(cycle_result):
            from_path = row.get("from_path", "")
            to_path = row.get("to_path", "")
            cycle_key = ":".join(sorted([from_path, to_path]))
            if cycle_key in seen_cycles:
                continue
            seen_cycles.add(cycle_key)
            from_name = from_path.split("/")[-1] if from_path else "?"
            to_name = to_path.split("/")[-1] if to_path else "?"
            recs.append(
                {
                    "id": _rec_id(f"cycle:{cycle_key}"),
                    "type": "risk",
                    "title": f"Circular dependency: {from_name} <-> {to_name}",
                    "description": (
                        "These files import each other, creating a circular dependency. "
                        "This can cause import errors and makes refactoring harder."
                    ),
                    "action": "fix",
                    "action_prompt": (
                        f"Break the circular dependency between {from_path} and {to_path}. "
                        f"Identify which direction is primary and extract shared logic into "
                        f"a third module if needed."
                    ),
                    "severity": "high",
                    "source": "graph_analysis",
                    "related_files": [from_path, to_path],
                }
            )

        # --- Untested source files ---
        untested_result = await db.query(
            """
            SELECT path, name, change_frequency
            FROM graph_file
            WHERE graph_id = $gid
              AND path !~ 'test'
              AND path !~ '__pycache__'
              AND path !~ 'node_modules'
              AND change_frequency > 3
            ORDER BY change_frequency DESC
            LIMIT 20
            """,
            {"gid": graph_id},
        )
        untested_files = parse_rows(untested_result)

        test_result = await db.query(
            """
            SELECT path FROM graph_file
            WHERE graph_id = $gid AND path ~ 'test'
            """,
            {"gid": graph_id},
        )
        test_paths = {r.get("path", "") for r in parse_rows(test_result)}

        for f in untested_files[:5]:
            path = f.get("path", "")
            name = f.get("name", "")
            # Check if a test file exists for this module
            base = path.replace("/", "_").replace(".", "_")
            has_test = any(base in tp or name.replace(".py", "") in tp for tp in test_paths)
            if not has_test and path:
                churn = f.get("change_frequency", 0)
                recs.append(
                    {
                        "id": _rec_id(f"untested:{path}"),
                        "type": "suggestion",
                        "title": f"No tests found for {name}",
                        "description": (
                            f"This file changes frequently ({churn} times) but has no "
                            f"corresponding test file. Adding tests prevents regressions."
                        ),
                        "action": "explore",
                        "action_prompt": (
                            f"Create tests for {path}. Focus on the main public functions "
                            f"and edge cases. Use pytest with the project's existing patterns."
                        ),
                        "severity": "low",
                        "source": "graph_analysis",
                        "related_files": [path],
                    }
                )
                if len(recs) > 10:
                    break

    return recs


# ---------------------------------------------------------------------------
# Analyzer 3: LLM-Powered Deep Analysis
# ---------------------------------------------------------------------------


async def _analyze_with_llm(
    graph_id: str,
    existing_recs: list[dict],
) -> list[dict]:
    """Take the top 3 most changed files and ask the LLM for improvement suggestions."""
    from core.engine.core.llm import llm

    async with pool.connection() as db:
        result = await db.query(
            """
            SELECT path, name, change_frequency
            FROM graph_file
            WHERE graph_id = $gid
            ORDER BY change_frequency DESC
            LIMIT 3
            """,
            {"gid": graph_id},
        )
        top_files = parse_rows(result)

    if not top_files:
        return []

    # Already-flagged paths — avoid duplicating advice
    flagged_paths = set()
    for r in existing_recs:
        flagged_paths.update(r.get("related_files", []))

    # Gather function names for each file
    file_sections: list[str] = []
    included_paths: list[str] = []
    async with pool.connection() as db:
        for f in top_files:
            path = f.get("path", "")
            func_result = await db.query(
                """
                SELECT name FROM graph_function
                WHERE graph_id = $gid AND file_path = $path
                ORDER BY name LIMIT 30
                """,
                {"gid": graph_id, "path": path},
            )
            funcs = [r.get("name", "") for r in parse_rows(func_result)]
            if funcs:
                file_sections.append(f"{path}: {', '.join(funcs)}")
                included_paths.append(path)

    if not file_sections:
        return []

    prompt = (
        "These are the most actively changed files in this codebase:\n"
        + "\n".join(file_sections)
        + "\n\nBased on the function names and patterns, suggest 2-3 specific improvements.\n"
        "Focus on: naming, complexity, missing error handling, deprecated patterns.\n"
        'Return JSON: {"recommendations": [{"title": "...", "description": "...", "action_prompt": "..."}]}'
    )

    try:
        data = await llm.complete_json(prompt, model=settings.llm_budget_model)
    except Exception:
        return []

    recs: list[dict] = []
    for item in data.get("recommendations", [])[:3]:
        title = item.get("title", "")
        if not title:
            continue
        rec_id = _rec_id(f"llm:{title}")
        recs.append(
            {
                "id": rec_id,
                "type": "suggestion",
                "title": title,
                "description": item.get("description", ""),
                "action": "review",
                "action_prompt": item.get("action_prompt", ""),
                "severity": "low",
                "source": "graph_analysis",
                "related_files": included_paths,
            }
        )

    return recs


# ---------------------------------------------------------------------------
# Analyzer 4: Self-Optimizer Proposals
# ---------------------------------------------------------------------------


async def _analyze_self_optimizer_proposals(graph_id: str) -> list[dict]:
    """Convert pending self-optimizer proposals into recommendations."""
    recs: list[dict] = []

    try:
        async with pool.connection() as db:
            result = await db.query(
                """
                SELECT * FROM self_optimizer_proposal
                WHERE status = 'pending'
                ORDER BY created_at DESC
                LIMIT 3
                """,
            )
            proposals = parse_rows(result)

        for p in proposals:
            pid = str(p.get("id", ""))
            name = p.get("name", p.get("title", "Optimization proposal"))
            desc = p.get("description", "")
            ptype = p.get("type", "improvement")

            recs.append(
                {
                    "id": _rec_id(f"proposal:{pid}"),
                    "type": "improvement",
                    "title": name,
                    "description": desc or f"ACE suggests a {ptype} improvement",
                    "action": "review",
                    "action_prompt": desc or f"Implement the proposed {ptype}: {name}",
                    "severity": "medium",
                    "source": "self_optimizer",
                    "related_files": [],
                    "_proposal_id": pid,
                }
            )
    except Exception as exc:
        logger.debug("Self-optimizer proposals query failed: %s", exc)

    return recs


# ---------------------------------------------------------------------------
# Analyzer 5: Stale Decision Detection
# ---------------------------------------------------------------------------


async def _analyze_stale_decisions(graph_id: str) -> list[dict]:
    """Find decisions older than 30 days about files that have changed since."""
    recs: list[dict] = []

    try:
        async with pool.connection() as db:
            result = await db.query(
                """
                SELECT *
                FROM graph_decision
                WHERE graph_id = $gid
                  AND timestamp < time::now() - 30d
                ORDER BY timestamp ASC
                LIMIT 5
                """,
                {"gid": graph_id},
            )
            decisions = parse_rows(result)

        for d in decisions:
            did = str(d.get("id", ""))
            title = d.get("title", d.get("name", "Untitled decision"))
            desc = d.get("description", d.get("summary", ""))
            related = d.get("related_files", d.get("files", []))
            if isinstance(related, str):
                related = [related]

            # Calculate age in days (rough estimate from string)
            age_label = "over 30 days ago"

            recs.append(
                {
                    "id": _rec_id(f"stale_decision:{did}"),
                    "type": "suggestion",
                    "title": f"Review: {title}",
                    "description": (
                        f"This decision was made {age_label}. The related code may have "
                        f"changed since then. Worth checking if it still applies."
                    ),
                    "action": "review",
                    "action_prompt": (
                        f"Review the decision '{title}': {desc}\n"
                        f"Check if the context has changed and whether the decision "
                        f"should be updated or confirmed."
                    ),
                    "severity": "low",
                    "source": "graph_analysis",
                    "related_files": related if isinstance(related, list) else [],
                }
            )
    except Exception as exc:
        logger.debug("Stale decision query failed: %s", exc)

    return recs
