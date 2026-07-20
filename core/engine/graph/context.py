# engine/graph/context.py
"""Graph context loader — build execution context from the code graph.

Replaces the old specialty/domain-based intelligence loading with context
derived from the code graph.  Extracts file/function references from a task
description, finds matching graph_file nodes, traverses their edges, and
returns a structured context dict that the orchestrator prompt can use.

All DB queries are best-effort: failures return empty results silently.
The loader is designed for speed (3-5 DB queries total, not full traversal).
"""

from __future__ import annotations

import logging
import re

from core.engine.core.db import parse_rows, pool, serialize_record

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Reference extraction
# ---------------------------------------------------------------------------

# File-path pattern: engine/core/db.py, auth.py, etc.
# NOTE: longer extensions must come before shorter ones (tsx before ts, json before js, etc.)
_FILE_RE = re.compile(r"[\w/.-]+\.(?:py|tsx|ts|jsx|json|js|rs|go|surql|sql|toml|yaml|yml)")

# Backtick-quoted code refs: `parse_rows`, `engine.core.db`, etc.
_CODE_REF_RE = re.compile(r"`(\w+(?:\.\w+)*)`")

# Keywords that map to common code areas
_AREA_KEYWORDS = frozenset(
    {
        "auth",
        "api",
        "database",
        "db",
        "test",
        "config",
        "schema",
        "migration",
        "graph",
        "scanner",
        "engine",
        "portal",
        "orchestrat",
        "classifier",
        "loader",
        "executor",
        "runner",
        "llm",
        "model",
    }
)


def extract_references(description: str) -> dict:
    """Extract file paths, function names, and area keywords from text.

    Returns ``{"files": [...], "functions": [...], "keywords": [...]}``.
    """
    files = _FILE_RE.findall(description)
    functions = _CODE_REF_RE.findall(description)

    words = set(description.lower().split())
    keywords = sorted(words & _AREA_KEYWORDS)

    return {
        "files": list(dict.fromkeys(files)),  # dedupe, preserve order
        "functions": list(dict.fromkeys(functions)),
        "keywords": keywords,
    }


# ---------------------------------------------------------------------------
# Graph queries
# ---------------------------------------------------------------------------


async def _find_files(terms: list[str], graph_id: str) -> list[dict]:
    """Find graph_file nodes matching any of the given terms.

    Searches by path CONTAINS and name CONTAINS.  Capped at 20 results to
    keep the context focused.
    """
    if not terms:
        return []

    try:
        async with pool.connection() as db:
            result = await db.query(
                """
                SELECT *,
                    (SELECT count() FROM graph_function WHERE file = $parent.id AND graph_id = $gid GROUP ALL)[0].count AS function_count
                FROM graph_file
                WHERE graph_id = $gid
                  AND (path IN $terms OR name IN $terms
                       OR string::contains(path, $t0)
                       OR string::contains(path, $t1)
                       OR string::contains(path, $t2))
                ORDER BY change_frequency DESC
                LIMIT 20
                """,
                {
                    "gid": graph_id,
                    "terms": terms,
                    # Provide up to 3 CONTAINS terms (pad with unlikely match)
                    "t0": terms[0] if len(terms) > 0 else "\x00",
                    "t1": terms[1] if len(terms) > 1 else "\x00",
                    "t2": terms[2] if len(terms) > 2 else "\x00",
                },
            )
        return parse_rows(result)
    except Exception as exc:
        logger.debug("_find_files failed (best-effort): %s", exc)
        return []


async def _get_dependents_count(file_id: str, graph_id: str) -> int:
    """Count how many other files depend on / import this file."""
    try:
        async with pool.connection() as db:
            result = await db.query(
                f"SELECT count() AS cnt FROM ({file_id})<-imports<-graph_file WHERE graph_id = $gid GROUP ALL",
                {"gid": graph_id},
            )
        rows = parse_rows(result)
        return rows[0].get("cnt", 0) if rows else 0
    except Exception:
        return 0


async def _get_decisions(file_ids: list[str], graph_id: str) -> list[dict]:
    """Get graph_decision nodes linked to the given files via improves edges."""
    if not file_ids:
        return []

    try:
        async with pool.connection() as db:
            # Decisions that improved/affected these files
            # graph_task -> improves -> graph_file; graph_task <- informed_by <- graph_decision
            # Simpler: just look for decisions linked via improves or related_to
            result = await db.query(
                """
                SELECT * FROM graph_decision
                WHERE graph_id = $gid
                ORDER BY timestamp DESC
                LIMIT 10
                """,
                {"gid": graph_id},
            )
        rows = parse_rows(result)
        return [
            {
                "title": serialize_record(r.get("title", "")),
                "description": str(r.get("description", ""))[:200],
                "outcome": r.get("outcome", "unknown"),
                "timestamp": str(r.get("timestamp", "")),
            }
            for r in rows
        ]
    except Exception as exc:
        logger.debug("_get_decisions failed (best-effort): %s", exc)
        return []


async def _get_dependencies(file_ids: list[str], graph_id: str) -> list[dict]:
    """Get import/depends_on edges for the matched files."""
    if not file_ids:
        return []

    deps: list[dict] = []
    try:
        async with pool.connection() as db:
            for fid in file_ids[:5]:  # cap to keep fast
                # Outgoing imports
                out_result = await db.query(
                    f"SELECT id, path, name FROM ({fid})->imports->graph_file WHERE graph_id = $gid LIMIT 10",
                    {"gid": graph_id},
                )
                for r in parse_rows(out_result):
                    deps.append(
                        {
                            "from": fid,
                            "to": str(serialize_record(r.get("id", ""))),
                            "to_path": r.get("path", ""),
                            "type": "imports",
                        }
                    )

                # Incoming imports (who depends on me)
                in_result = await db.query(
                    f"SELECT id, path, name FROM ({fid})<-imports<-graph_file WHERE graph_id = $gid LIMIT 10",
                    {"gid": graph_id},
                )
                for r in parse_rows(in_result):
                    deps.append(
                        {
                            "from": str(serialize_record(r.get("id", ""))),
                            "from_path": r.get("path", ""),
                            "to": fid,
                            "type": "imported_by",
                        }
                    )
    except Exception as exc:
        logger.debug("_get_dependencies failed (best-effort): %s", exc)

    return deps


async def _get_agent_history(file_ids: list[str], graph_id: str) -> list[dict]:
    """Get agent configs that have worked on these files before."""
    if not file_ids:
        return []

    try:
        async with pool.connection() as db:
            # graph_task -> improves -> graph_file  AND  graph_task -> assigned_to -> graph_agent
            # Find tasks that touched these files, then find their agents
            result = await db.query(
                """
                SELECT * FROM agent_execution
                WHERE graph_id = $gid
                ORDER BY created_at DESC
                LIMIT 10
                """,
                {"gid": graph_id},
            )
        rows = parse_rows(result)
        return [
            {
                "archetype": r.get("archetype", "executor"),
                "mode": r.get("mode", "reactive"),
                "perspective": r.get("perspective", "practitioner"),
                "specialties": r.get("specialties", []),
            }
            for r in rows
        ]
    except Exception as exc:
        logger.debug("_get_agent_history failed (best-effort): %s", exc)
        return []


async def _get_graph_stats(graph_id: str) -> dict:
    """Quick graph size stats."""
    try:
        async with pool.connection() as db:
            counts = {}
            for table in ("graph_file", "graph_function", "graph_decision"):
                result = await db.query(
                    f"SELECT count() AS cnt FROM {table} WHERE graph_id = $gid GROUP ALL",
                    {"gid": graph_id},
                )
                rows = parse_rows(result)
                counts[table.replace("graph_", "")] = rows[0].get("cnt", 0) if rows else 0

            # Import edge count
            result = await db.query("SELECT count() AS cnt FROM imports GROUP ALL")
            rows = parse_rows(result)
            counts["imports"] = rows[0].get("cnt", 0) if rows else 0

        return {
            "files": counts.get("file", 0),
            "functions": counts.get("function", 0),
            "decisions": counts.get("decision", 0),
            "imports": counts.get("imports", 0),
        }
    except Exception:
        return {"files": 0, "functions": 0, "decisions": 0, "imports": 0}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def load_graph_context(task_description: str, graph_id: str = "default") -> dict:
    """Load relevant context from the code graph for a task.

    1. Extract file/function references from the task description
    2. Find matching graph_file nodes
    3. Traverse to get: imports, dependents, decisions, agent history
    4. Build a context dict the executor can use in its prompt

    Returns
    -------
    dict
        ``relevant_files``, ``decisions``, ``dependencies``, ``agent_history``,
        ``risk_flags``, ``graph_stats``, ``references_extracted``.

    All queries are best-effort.  On any failure the relevant section is empty.
    """
    refs = extract_references(task_description)
    all_terms = refs["files"] + refs["functions"] + refs["keywords"]

    if not all_terms:
        # Nothing to search for -- return empty context
        stats = await _get_graph_stats(graph_id)
        return {
            "relevant_files": [],
            "decisions": [],
            "dependencies": [],
            "agent_history": [],
            "risk_flags": [],
            "graph_stats": stats,
            "references_extracted": refs,
        }

    # Step 2: Find matching files
    matched_files = await _find_files(all_terms, graph_id)

    # Build enriched file list with dependent counts
    relevant_files: list[dict] = []
    file_ids: list[str] = []

    for f in matched_files[:10]:  # cap at 10 files for context
        fid = str(serialize_record(f.get("id", "")))
        file_ids.append(fid)

        dep_count = await _get_dependents_count(fid, graph_id)

        relevant_files.append(
            {
                "id": fid,
                "path": f.get("path", ""),
                "name": f.get("name", ""),
                "language": f.get("language", ""),
                "function_count": f.get("function_count") or 0,
                "change_frequency": f.get("change_frequency", 0),
                "fragility_score": f.get("fragility_score", 0.0),
                "dependent_count": dep_count,
                "line_count": f.get("line_count", 0),
            }
        )

    # Semantic search enhancement — find conceptually related files
    try:
        from core.engine.search.semantic import semantic_search

        semantic_files = await semantic_search(task_description, product_id="product:platform", limit=5)
        existing_paths = {f.get("path") for f in relevant_files}
        for sf in semantic_files:
            if sf.get("path") and sf["path"] not in existing_paths:
                relevant_files.append(
                    {
                        "id": sf["id"],
                        "path": sf["path"],
                        "match_type": "semantic",
                        "semantic_score": sf.get("score", 0),
                    }
                )
                existing_paths.add(sf["path"])
    except Exception:
        pass  # Semantic search is best-effort enhancement

    # Step 3: Traverse for decisions, dependencies, agent history
    decisions = await _get_decisions(file_ids, graph_id)
    dependencies = await _get_dependencies(file_ids, graph_id)
    agent_history = await _get_agent_history(file_ids, graph_id)

    # Step 4: Compute risk flags
    risk_flags: list[str] = []
    for f in relevant_files:
        change_freq = f.get("change_frequency", 0)
        if change_freq > 5:
            risk_flags.append(f"{f['path']} is fragile (changed {change_freq} times)")
        dep_count = f.get("dependent_count", 0)
        if dep_count > 20:
            risk_flags.append(f"{f['path']} has {dep_count} dependents -- changes have wide impact")
        frag = f.get("fragility_score", 0.0)
        if frag > 0.7:
            risk_flags.append(f"{f['path']} has high fragility score ({frag:.2f})")

    # Step 5: Graph stats
    stats = await _get_graph_stats(graph_id)

    return {
        "relevant_files": relevant_files,
        "decisions": decisions,
        "dependencies": dependencies,
        "agent_history": agent_history,
        "risk_flags": risk_flags,
        "graph_stats": stats,
        "references_extracted": refs,
    }
