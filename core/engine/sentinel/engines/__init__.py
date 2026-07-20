# engine/sentinel/engines/__init__.py
"""Shared helpers for overnight engines.

Every engine writes insights via write_engine_insight() and queues research
via queue_research(). These helpers enforce provenance, respect flow control,
and prevent duplication across engines.

Spec: docs/superpowers/specs/2026-03-21-phase3b-overnight-engines.md
"""

from __future__ import annotations


async def write_engine_insight(
    db,
    *,
    product_id: str,
    content: str,
    insight_type: str,
    tier: str,
    discipline: str,
    source_domain: str,
    confidence: float,
    tags: list[str],
    source_task: str | None = None,
) -> str:
    """Write an insight with provenance, respecting flow control.

    Args:
        db: SurrealDB connection (already acquired from pool).
        product_id: The org this insight belongs to.
        content: The insight text content.
        insight_type: One of: fact, pattern, preference, correction, procedure.
        tier: One of: specialty, subdomain, domain, org.
        discipline: Discipline tag used for routing (e.g. "frontend", "devops").
        source_domain: Provenance tag, e.g. "sentinel.failure-analysis".
        confidence: Float 0.0-1.0.
        tags: List of tag strings for categorization.
        source_task: Optional task record ID that triggered this insight.

    Returns:
        The created insight record ID string.
    """
    from core.engine.capture.synthesizer import _route_to_graph
    from core.engine.core.db import parse_one, parse_rows

    # Determine which graph this insight belongs to
    graph = _route_to_graph(insight_type)

    # Resolve specialty record ID for specialty-graph insights
    specialty_id = None
    if graph == "specialty" and discipline:
        spec_rows = parse_rows(
            await db.query(
                "SELECT id, slug FROM specialty WHERE product = <record>$product AND tags CONTAINS $discipline LIMIT 1",
                {"product": product_id, "discipline": discipline},
            )
        )
        if spec_rows:
            specialty_id = spec_rows[0].get("id")

    # Build the CREATE query
    source_task_clause = ", source_task = $source_task" if source_task else ""

    # Ensure discipline is in tags for queryability
    effective_tags = list(tags)
    if discipline and discipline not in effective_tags:
        effective_tags = [discipline, *effective_tags]

    result = await db.query(
        f"""
        CREATE insight SET
            product = <record>$product,
            content = $content,
            insight_type = $insight_type,
            tier = $tier,
            specialty = $specialty,
            source_domain = $source_domain,
            confidence = $confidence,
            tags = $tags,
            status = 'active',
            last_confirmed = time::now(),
            created_at = time::now(),
            updated_at = time::now()
            {source_task_clause}
        """,
        {
            "product": product_id,
            "content": content,
            "insight_type": insight_type,
            "tier": tier,
            "specialty": specialty_id,
            "source_domain": source_domain,
            "confidence": confidence,
            "tags": effective_tags,
            **({"source_task": source_task} if source_task else {}),
        },
    )

    row = parse_one(result)
    insight_id_str = str(row.get("id", "")) if row else ""

    # Dual-write to graph (best-effort)
    if insight_id_str:
        try:
            from core.engine.capture.synthesizer import _safe_confidence
            from core.engine.graph.insight_writer import write_insight_to_graph

            await write_insight_to_graph(
                insight_id=insight_id_str,
                content=content,
                insight_type=insight_type,
                confidence=_safe_confidence(confidence),
                source="overnight",
                tags=effective_tags,
                specialty_slug=None,
                task_id=source_task,
            )
        except Exception:
            pass  # graph write is best-effort

    return insight_id_str


async def load_discipline_context(discipline: str, product_id: str) -> str:
    """Load existing graph intelligence for a discipline, formatted for LLM injection.

    Returns a markdown section with the top-confidence insights, or "" when
    nothing is loaded (missing discipline, empty graph, loader failure).
    Loads in "deliberative" mode so recent observations are included.
    """
    if not discipline or not product_id:
        return ""
    try:
        from core.engine.orchestrator.loader import load_intelligence

        snapshot = await load_intelligence(
            discipline=discipline,
            product_id=product_id,
            mode="deliberative",
        )
        insights = snapshot.get("insights", [])
        if not insights:
            return ""
        lines = [f"- [{i.get('confidence', 0):.0%}] {i.get('content', '')}" for i in insights[:8]]
        return "## Existing Knowledge for This Discipline\n" + "\n".join(lines)
    except Exception:
        return ""


async def queue_research(
    db,
    *,
    product_id: str,
    query: str,
    context: str,
    priority: str,
    source: str,
    related_task: str | None = None,
) -> str:
    """Queue a research item for the gap researcher.

    Args:
        db: SurrealDB connection (already acquired from pool).
        product_id: The org this research belongs to.
        query: The research question.
        context: Context explaining why this research is needed.
        priority: One of: low, medium, high, critical.
        source: Who queued it: failure-analysis, specialty-deepener, user-request, conflict-detector, ecosystem-scanner.
        related_task: Optional task record ID that prompted this research.

    Returns:
        The created research_queue record ID string.
    """
    related_task_clause = ", related_task = <record>$related_task" if related_task else ""

    from core.engine.core.db import parse_one

    result = await db.query(
        f"""
        CREATE research_queue SET
            product = <record>$product,
            query = $query,
            context = $context,
            priority = $priority,
            source = $source,
            status = 'pending',
            created_at = time::now()
            {related_task_clause}
        """,
        {
            "product": product_id,
            "query": query,
            "context": context,
            "priority": priority,
            "source": source,
            **({"related_task": related_task} if related_task else {}),
        },
    )

    row = parse_one(result)
    return str(row.get("id", "")) if row else ""
