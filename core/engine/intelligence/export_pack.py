"""Prompt pack export — portable intelligence bundle.

Emits a single markdown document capturing a product's learned intelligence for
a given discipline. The output is LLM-agnostic: any agent/model can prepend this
to its system prompt and gain ACE's accumulated knowledge without a live ACE
runtime in the loop.

Shape:
    # ACE Intelligence Pack
    > Product: product:platform  ·  Discipline: security  ·  Generated: <iso>

    ## Expert Knowledge
    - [0.95] SurrealDB v3 requires <record> casts for record refs
    - [0.90] Always use get_llm() not raw ClaudeProvider

    ## Decisions
    - **Use Postgres** — ACID guarantees
      - alternatives considered: MongoDB

    ## Proven Reasoning Patterns
    - refactor auth → succeeded at 0.88 confidence
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_DEFAULT_LIMIT = 50


async def export_prompt_pack(
    db,
    product_id: str,
    discipline: str,
    limit: int = _DEFAULT_LIMIT,
) -> str:
    """Assemble a markdown prompt pack for the given (product, discipline).

    Non-fatal on partial DB failures — returns a minimally-valid pack with a
    warning rather than propagating.
    """
    from core.engine.core.db import parse_rows

    generated_at = datetime.now(timezone.utc).isoformat()
    lines: list[str] = [
        "# ACE Intelligence Pack",
        f"> Product: {product_id}  ·  Discipline: {discipline}  ·  Generated: {generated_at}",
        "",
        "Prepend this document to any agent's system prompt to inherit ACE's accumulated",
        f"intelligence for **{discipline}** on this product.",
        "",
    ]

    # Section 1: Insights (ranked by confidence × utilization)
    insights = (await _safe_fetch_insights(db, product_id, discipline, limit))[:limit]
    if insights:
        lines.append("## Expert Knowledge")
        for ins in insights:
            conf = float(ins.get("confidence", 0.5) or 0.5)
            content = (ins.get("content") or "").strip()
            if content:
                lines.append(f"- [{conf:.2f}] {content}")
        lines.append("")
    else:
        lines.append("## Expert Knowledge")
        lines.append("_No insights captured for this discipline yet._")
        lines.append("")

    # Section 2: Decisions (active / not superseded)
    decisions = (await _safe_fetch_decisions(db, product_id, discipline, limit))[:limit]
    if decisions:
        lines.append("## Decisions")
        for d in decisions:
            title = (d.get("title") or "").strip()
            rationale = (d.get("rationale") or "").strip()
            alts = d.get("alternatives") or []
            if title:
                lines.append(f"- **{title}** — {rationale}")
                if alts:
                    lines.append(f"  - alternatives: {', '.join(str(a) for a in alts[:5])}")
        lines.append("")

    # Section 3: Corrections — captured mistakes + the right answer
    corrections = (await _safe_fetch_corrections(db, product_id, discipline, limit))[:limit]
    if corrections:
        lines.append("## Corrections")
        for c in corrections:
            content = (c.get("content") or "").strip()
            if content:
                lines.append(f"- {content}")
        lines.append("")

    # Section 4: STaR traces — successful reasoning patterns as few-shot examples
    traces = (await _safe_fetch_star_traces(db, product_id, discipline, limit))[:limit]
    if traces:
        lines.append("## Proven Reasoning Patterns")
        for t in traces:
            desc = (t.get("task_description") or "").strip()
            conf = float(t.get("confidence", 0.5) or 0.5)
            if desc:
                lines.append(f"- {desc[:160]} — succeeded at {conf:.2f} confidence")
        lines.append("")

    # If everything was empty, leave a helpful marker so readers know it's valid-but-empty
    has_any_data = bool(insights or decisions or corrections or traces)
    if not has_any_data:
        lines.append("_No data yet for this discipline. Run ACE tasks to accumulate intelligence._")

    # Swallow parse_rows import reference so linter keeps the import used in helpers
    _ = parse_rows
    return "\n".join(lines)


async def _safe_fetch_insights(db, product_id: str, discipline: str, limit: int) -> list[dict]:
    try:
        from core.engine.core.db import parse_rows

        result = await db.query(
            """SELECT content, confidence, tier FROM insight
               WHERE product = <record>$product
                 AND status = 'active'
                 AND (tags CONTAINS $disc OR source_domain = $disc OR discipline_hint = $disc)
               ORDER BY confidence DESC
               LIMIT $limit""",
            {"product": product_id, "disc": discipline, "limit": limit},
        )
        return parse_rows(result)
    except Exception as exc:
        logger.warning("export_pack: insights fetch failed: %s", exc)
        return []


async def _safe_fetch_decisions(db, product_id: str, discipline: str, limit: int) -> list[dict]:
    try:
        from core.engine.core.db import parse_rows

        result = await db.query(
            """SELECT title, rationale, alternatives, created_at FROM decision
               WHERE product = <record>$product
                 AND outcome = 'accepted'
                 AND (discipline_hint = $disc OR decision_type = $disc OR discipline_hint IS NONE)
               ORDER BY created_at DESC
               LIMIT $limit""",
            {"product": product_id, "disc": discipline, "limit": limit},
        )
        return parse_rows(result)
    except Exception as exc:
        logger.warning("export_pack: decisions fetch failed: %s", exc)
        return []


async def _safe_fetch_corrections(db, product_id: str, discipline: str, limit: int) -> list[dict]:
    try:
        from core.engine.core.db import parse_rows

        result = await db.query(
            """SELECT content, confidence FROM insight
               WHERE product = <record>$product
                 AND status = 'active'
                 AND insight_type = 'correction'
                 AND (tags CONTAINS $disc OR source_domain = $disc OR discipline_hint = $disc)
               ORDER BY confidence DESC
               LIMIT $limit""",
            {"product": product_id, "disc": discipline, "limit": limit},
        )
        return parse_rows(result)
    except Exception as exc:
        logger.warning("export_pack: corrections fetch failed: %s", exc)
        return []


async def _safe_fetch_star_traces(db, product_id: str, discipline: str, limit: int) -> list[dict]:
    try:
        from core.engine.core.db import parse_rows

        result = await db.query(
            """SELECT task_description, final_output, confidence FROM star_trace
               WHERE product = <record>$product
                 AND discipline = $disc
               ORDER BY confidence DESC
               LIMIT $limit""",
            {"product": product_id, "disc": discipline, "limit": limit},
        )
        return parse_rows(result)
    except Exception as exc:
        logger.warning("export_pack: traces fetch failed: %s", exc)
        return []
