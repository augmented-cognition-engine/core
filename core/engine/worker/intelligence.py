# engine/worker/intelligence.py
"""Progressive Intelligence Loader — compact index for hook injection.

Instead of dumping top-5 insights every message (~1000 tokens), we build
a ~200-token compact index that gives the LLM pointers. The LLM fetches
detail via ace_load / ace_search when it needs specifics.

Format returned:
    ## Context (use ace_load for detail)
    - [ux] 2 decisions, 5 insights, 1 active capability
    - [arch] locked_aesthetic_direction: "dark, dense" (decision:xyz)
    - [session] exploring cognitive composition architecture (12 msgs)

Token budget: ~200–300 tokens for the index. Full detail on demand.
"""

from __future__ import annotations

import logging

from core.engine.core.db import parse_rows, pool

logger = logging.getLogger(__name__)

# Max tokens for the compact index (rough estimate: 1 token ≈ 4 chars)
_MAX_INDEX_CHARS = 1200  # ~300 tokens


async def build_compact_index(
    discipline: str,
    session_summary: str,
    message_count: int,
    product_id: str = "product:platform",
) -> str:
    """Build a ~200-300 token compact intelligence index for hook injection.

    Queries insights, decisions, and capabilities by discipline. Returns a
    concise pointer index — not full content. Designed to fit in a Claude
    system prompt without consuming the conversation context budget.
    """
    lines = ["## Context (use ace_load for detail)"]

    try:
        async with pool.connection() as db:
            # 1. Insight count by discipline
            insight_result = await db.query(
                """SELECT count() AS n FROM insight
                WHERE product = <record>$product AND status = 'active'
                AND (discipline_hint = $disc OR domain_path = $disc)
                AND confidence >= 0.6
                GROUP ALL""",
                {"product": product_id, "disc": discipline},
            )
            insight_rows = parse_rows(insight_result)
            insight_count = insight_rows[0].get("n", 0) if insight_rows else 0

            # 2. Decision count + latest title by discipline
            # NOTE: created_at must be in SELECT for ORDER BY to work in SurrealDB v3
            decision_result = await db.query(
                """SELECT title, decision_type, id, created_at FROM decision
                WHERE product = <record>$product AND status = 'active'
                AND discipline_hint = $disc
                ORDER BY created_at DESC LIMIT 3""",
                {"product": product_id, "disc": discipline},
            )
            decisions = parse_rows(decision_result)

            # 3. Active capability count
            cap_result = await db.query(
                """SELECT count() AS n FROM graph_capability
                WHERE product = <record>$product AND quality_score >= 0.5
                GROUP ALL""",
                {"product": product_id},
            )
            cap_rows = parse_rows(cap_result)
            cap_count = cap_rows[0].get("n", 0) if cap_rows else 0

            # 4. Global insight count
            global_result = await db.query(
                """SELECT count() AS n FROM insight
                WHERE product = <record>$product AND status = 'active'
                AND confidence >= 0.65
                GROUP ALL""",
                {"product": product_id},
            )
            global_rows = parse_rows(global_result)
            global_count = global_rows[0].get("n", 0) if global_rows else 0

    except Exception as exc:
        logger.debug("build_compact_index DB query failed: %s", exc)
        return ""

    # Build the compact index lines
    disc_parts = []
    if decisions:
        disc_parts.append(f"{len(decisions)} decisions")
    if insight_count:
        disc_parts.append(f"{insight_count} insights")
    if cap_count:
        disc_parts.append(f"{cap_count} capabilities")

    if disc_parts:
        lines.append(f"- [{discipline}] {', '.join(disc_parts)}")

    # Top decision titles as pointers (not full content)
    for d in decisions[:2]:
        title = d.get("title", "?")[:80]
        rec_id = str(d.get("id", "")).split(":")[-1][:12]
        lines.append(f"  → {title} (decision:{rec_id})")

    # Global intelligence summary
    if global_count > 0:
        lines.append(f"- [global] {global_count} insights available — ace_search to query")

    # Session context pointer
    if session_summary and message_count > 2:
        summary_snippet = session_summary[:120].replace("\n", " ")
        lines.append(f"- [session] {summary_snippet} ({message_count} msgs)")

    result = "\n".join(lines)

    # Enforce token budget
    if len(result) > _MAX_INDEX_CHARS:
        result = result[: _MAX_INDEX_CHARS - 3] + "..."

    return result if len(lines) > 1 else ""
