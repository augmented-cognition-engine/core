# engine/product/decision_linker.py
"""Auto-link decisions to capabilities and git commits via keyword matching.

After ace_capture_decision stores deliberate PM decisions, this module enriches
the graph by finding related capabilities and commits — enabling traceability
from any node in either direction.

Edge types written:
  decision -> affected    -> capability      (already used by ace_capture_decision)
  decision -> manifested_by -> graph_decision  (new: which commits implement this decision)
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Common English stop words excluded from keyword matching
_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "must",
        "shall",
        "can",
        "from",
        "to",
        "for",
        "in",
        "on",
        "at",
        "by",
        "with",
        "of",
        "or",
        "and",
        "but",
        "not",
        "no",
        "if",
        "this",
        "that",
        "these",
        "those",
        "then",
        "than",
        "when",
        "where",
        "who",
        "what",
        "which",
        "how",
        "all",
        "any",
        "both",
        "each",
        "few",
        "more",
        "most",
        "other",
        "some",
        "such",
        "into",
        "through",
        "over",
        "about",
        "up",
        "out",
        "use",
        "using",
        "used",
        "make",
        "makes",
        "made",
        "add",
        "adds",
        "added",
        "new",
        "now",
        "also",
        "only",
        "just",
        "so",
        "via",
        "vs",
        "we",
        "our",
        "as",
        "it",
        "its",
        "after",
        "before",
    }
)


def _extract_keywords(text: str) -> frozenset[str]:
    """Extract meaningful lowercase keywords from text, stripping stop words."""
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9_\-]*", text.lower())
    return frozenset(w for w in words if len(w) >= 3 and w not in _STOP_WORDS)


def _overlap_score(kw_a: frozenset[str], kw_b: frozenset[str]) -> float:
    """Overlap coefficient: |intersection| / min(|A|, |B|).

    Chosen over Jaccard because decisions tend to be shorter texts than commit
    histories — a small focused overlap should score high even when one set is
    much larger.
    """
    if not kw_a or not kw_b:
        return 0.0
    return len(kw_a & kw_b) / min(len(kw_a), len(kw_b))


async def link_decisions(
    product_id: str,
    dry_run: bool = False,
    min_overlap: float = 0.25,
    max_commits_per_decision: int = 8,
) -> dict:
    """Link decisions to capabilities and git commits via keyword overlap.

    For each decision record in the `decision` table:
    - Find capabilities whose slug/name/description overlaps with the decision text
    - Find graph_decision (commit) records whose title/body overlaps
    - Create `affected` edges (decision → capability) and
      `manifested_by` edges (decision → graph_decision)

    Skips edges that already exist (idempotent — safe to re-run).

    Args:
        product_id:  Product to process (e.g. "product:platform")
        dry_run:     If True, returns what would be linked but writes nothing
        min_overlap: Minimum overlap coefficient (0-1) to create a link
        max_commits_per_decision: Cap on commit links per decision (highest-scoring)

    Returns dict with counts and per-decision breakdown.
    """
    from core.engine.core.db import parse_rows, pool
    from core.engine.graph.edge_writer import create_edge

    stats: dict = {
        "decisions_processed": 0,
        "capability_links_created": 0,
        "commit_links_created": 0,
        "dry_run": dry_run,
        "links": [],
    }

    async with pool.connection() as db:
        # Only link intentional PM decisions (mcp, agent_session, spec_generator).
        # Synthesizer-captured observations are intelligence signals, not architectural choices.
        decisions = parse_rows(
            await db.query(
                "SELECT * FROM decision WHERE product = <record>$product "
                "AND source IN ['mcp', 'agent_session', 'spec_generator', NONE]",
                {"product": product_id},
            )
        )
        if not decisions:
            return stats

        capabilities = parse_rows(
            await db.query(
                "SELECT id, slug, name, description FROM capability WHERE product = <record>$product",
                {"product": product_id},
            )
        )

        commits = parse_rows(
            await db.query("SELECT id, title, description FROM graph_decision WHERE graph_id = 'default' LIMIT 500")
        )

    # Pre-compute keyword sets (avoids re-computing inside the nested loop)
    cap_kw = {
        str(c["id"]): _extract_keywords(f"{c.get('slug', '')} {c.get('name', '')} {c.get('description', '')}")
        for c in capabilities
    }
    commit_kw = {str(c["id"]): _extract_keywords(f"{c.get('title', '')} {c.get('description', '')}") for c in commits}

    for decision in decisions:
        dec_id = str(decision["id"])
        dec_kw = _extract_keywords(
            f"{decision.get('title', '')} {decision.get('rationale', '')} {decision.get('decision_type', '')}"
        )
        if not dec_kw:
            stats["decisions_processed"] += 1
            continue

        async with pool.connection() as db:
            # Existing affected edges → skip re-creation
            existing_caps = {
                str(r["out"])
                for r in parse_rows(
                    await db.query(
                        "SELECT out FROM affected WHERE in = <record>$d",
                        {"d": dec_id},
                    )
                )
            }
            # Existing manifested_by edges → skip re-creation
            existing_commits = {
                str(r["out"])
                for r in parse_rows(
                    await db.query(
                        "SELECT out FROM manifested_by WHERE in = <record>$d",
                        {"d": dec_id},
                    )
                )
            }

        # Score capabilities
        new_caps: list[tuple[str, str, float]] = []
        for cap in capabilities:
            cap_id = str(cap["id"])
            if cap_id in existing_caps:
                continue
            score = _overlap_score(dec_kw, cap_kw[cap_id])
            if score >= min_overlap:
                new_caps.append((cap_id, cap.get("slug", cap_id), score))
        new_caps.sort(key=lambda x: x[2], reverse=True)

        # Score commits — cap at max_commits_per_decision
        new_commits: list[tuple[str, str, float]] = []
        for commit in commits:
            commit_id = str(commit["id"])
            if commit_id in existing_commits:
                continue
            score = _overlap_score(dec_kw, commit_kw[commit_id])
            if score >= min_overlap:
                new_commits.append((commit_id, commit.get("title", "")[:70], score))
        new_commits.sort(key=lambda x: x[2], reverse=True)
        new_commits = new_commits[:max_commits_per_decision]

        if not dry_run:
            for cap_id, _, _ in new_caps:
                result = await create_edge("affected", dec_id, cap_id)
                if result:
                    stats["capability_links_created"] += 1
                    # Emit typed canvas event for each new edge
                    try:
                        from core.engine.events.canvas import emit_edge_added

                        await emit_edge_added(
                            product_id=product_id,
                            edge_type="affected",
                            from_id=dec_id,
                            to_id=cap_id,
                            actor_id="decision_linker",
                        )
                    except Exception:
                        pass

            if new_commits:
                from surrealdb import RecordID as _RID

                dec_table, dec_rid = dec_id.split(":", 1)
                async with pool.connection() as db:
                    for commit_id, _, _ in new_commits:
                        try:
                            commit_table, commit_rid = commit_id.split(":", 1)
                            await db.query(
                                "RELATE $src -> manifested_by -> $dst "
                                "SET source = 'auto_linker', created_at = time::now()",
                                {
                                    "src": _RID(dec_table, dec_rid),
                                    "dst": _RID(commit_table, commit_rid),
                                },
                            )
                            stats["commit_links_created"] += 1
                        except Exception:
                            logger.debug("manifested_by edge skipped %s -> %s", dec_id, commit_id)
        else:
            stats["capability_links_created"] += len(new_caps)
            stats["commit_links_created"] += len(new_commits)
        stats["decisions_processed"] += 1

        if new_caps or new_commits:
            stats["links"].append(
                {
                    "decision": decision.get("title", dec_id),
                    "new_capabilities": [{"slug": slug, "score": round(score, 2)} for _, slug, score in new_caps],
                    "new_commits": [{"title": title, "score": round(score, 2)} for _, title, score in new_commits],
                }
            )

    return stats


async def trace_node(node_id: str) -> dict:
    """Traverse the graph from any node, returning all directly connected nodes.

    Understands these node types by ID prefix:
      decision:*      → capabilities, commits, specs
      capability:*    → decisions, files, specs
      graph_file:*    → functions, capabilities, commits
      graph_decision:* → decision, files

    Args:
        node_id: Full SurrealDB record ID (e.g. "decision:abc123")

    Returns dict with node details and connected nodes by relationship type.
    """
    from core.engine.core.db import parse_rows, pool

    table = node_id.split(":")[0] if ":" in node_id else ""

    async with pool.connection() as db:
        # Fetch the node itself
        node = parse_rows(await db.query("SELECT * FROM <record>$id", {"id": node_id}))
        if not node:
            return {"error": f"Node not found: {node_id}"}

        result: dict = {"node": node[0], "node_id": node_id, "connections": {}}

        if table == "decision":
            caps = parse_rows(
                await db.query(
                    "SELECT ->affected->capability.* AS caps FROM <record>$id",
                    {"id": node_id},
                )
            )
            commits = parse_rows(
                await db.query(
                    "SELECT ->manifested_by->graph_decision.{id, title, source_commit} AS commits FROM <record>$id",
                    {"id": node_id},
                )
            )
            specs = parse_rows(
                await db.query(
                    "SELECT ->led_to.* AS specs FROM <record>$id",
                    {"id": node_id},
                )
            )
            result["connections"]["capabilities"] = caps[0].get("caps", []) if caps else []
            result["connections"]["commits"] = commits[0].get("commits", []) if commits else []
            result["connections"]["specs"] = specs[0].get("specs", []) if specs else []

        elif table == "capability":
            decisions = parse_rows(
                await db.query(
                    "SELECT <-affected<-decision.{id, title, decision_type, rationale} AS decisions FROM <record>$id",
                    {"id": node_id},
                )
            )
            files = parse_rows(
                await db.query(
                    "SELECT <-realizes<-graph_file.{id, path, language} AS files FROM <record>$id",
                    {"id": node_id},
                )
            )
            result["connections"]["decisions"] = decisions[0].get("decisions", []) if decisions else []
            result["connections"]["files"] = files[0].get("files", []) if files else []

        elif table == "graph_file":
            caps = parse_rows(
                await db.query(
                    "SELECT ->realizes->capability.{id, slug, name} AS caps FROM <record>$id",
                    {"id": node_id},
                )
            )
            functions = parse_rows(
                await db.query(
                    "SELECT ->contains->graph_function.{id, name, kind} AS fns FROM <record>$id",
                    {"id": node_id},
                )
            )
            commits = parse_rows(
                await db.query(
                    "SELECT <-improves<-graph_decision.{id, title, source_commit} AS commits FROM <record>$id",
                    {"id": node_id},
                )
            )
            decisions_via_cap = parse_rows(
                await db.query(
                    "SELECT ->realizes->capability<-affected<-decision.{id, title} AS decisions FROM <record>$id",
                    {"id": node_id},
                )
            )
            result["connections"]["capabilities"] = caps[0].get("caps", []) if caps else []
            result["connections"]["functions"] = functions[0].get("fns", []) if functions else []
            result["connections"]["commits"] = commits[0].get("commits", []) if commits else []
            result["connections"]["decisions"] = decisions_via_cap[0].get("decisions", []) if decisions_via_cap else []

        elif table == "graph_decision":
            files = parse_rows(
                await db.query(
                    "SELECT ->improves->graph_file.{id, path} AS files FROM <record>$id",
                    {"id": node_id},
                )
            )
            decisions = parse_rows(
                await db.query(
                    "SELECT <-manifested_by<-decision.{id, title, decision_type} AS decisions FROM <record>$id",
                    {"id": node_id},
                )
            )
            result["connections"]["files"] = files[0].get("files", []) if files else []
            result["connections"]["decisions"] = decisions[0].get("decisions", []) if decisions else []

    return result
