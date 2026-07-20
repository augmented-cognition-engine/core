"""Product event handlers — close the feedback loop between product, execution, and intelligence.

Handlers:
- task.completed → create observation from task output (execution → intelligence)
- insight.created → check if insight addresses open gaps (intelligence → product)
- gap.detected → notify + queue for spec generation (product → execution)
- initiative.created → create observation for intelligence tracking
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def on_task_completed(event_type: str, payload: dict) -> None:
    """Feed completed task output into the capture pipeline as an observation.

    This bridges: execution → intelligence. Without this, task outputs
    disappear after being shown in chat.
    """
    output = payload.get("output", "")
    if not output or len(output) < 50:
        return  # Skip trivial outputs

    product_id = payload.get("product_id", "")
    discipline = payload.get("discipline", "")
    task_id = payload.get("task_id", "")

    try:
        from core.engine.core.db import pool

        async with pool.connection() as db:
            await db.query(
                """
                CREATE observation SET
                    content = $content,
                    observation_type = 'discovery',
                    confidence = 0.6,
                    discipline_hint = $discipline,
                    domain_hint = $discipline,
                    source = 'task_output',
                    source_task = $task_id,
                    synthesized = false,
                    created_at = time::now()
                """,
                {
                    "product": product_id,
                    "content": output[:2000],  # Cap at 2k chars
                    "discipline": discipline,
                    "task_id": task_id,
                },
            )
        logger.info("Task output captured as observation (task=%s, discipline=%s)", task_id, discipline)
    except Exception as exc:
        logger.warning("on_task_completed handler failed: %s", exc)


async def on_insight_created(event_type: str, payload: dict) -> None:
    """Check if newly created insights address any open quality gaps.

    This bridges: intelligence → product. Without this, insights accumulate
    but never improve product quality scores.
    """
    product_id = payload.get("product_id", "")
    if not product_id:
        return

    try:
        from core.engine.core.db import parse_rows, pool

        # Find low-score gaps that might be addressed by new insights
        async with pool.connection() as db:
            gaps = parse_rows(
                await db.query(
                    """
                SELECT capability.slug AS cap_slug, dimension, score, gaps
                FROM capability_quality
                WHERE product = <record>$product AND score < 0.4
                ORDER BY score ASC
                LIMIT 20
                """,
                    {"product": product_id},
                )
            )

        if not gaps:
            return

        # Count recent insights per discipline (last hour)
        async with pool.connection() as db:
            recent = parse_rows(
                await db.query(
                    """
                SELECT tags, count() AS cnt
                FROM insight
                WHERE product = <record>$product
                  AND created_at > time::now() - 1h
                GROUP BY tags
                """,
                    {"product": product_id},
                )
            )

        if not recent:
            return

        # Build set of recently active disciplines
        active_disciplines = set()
        for r in recent:
            for tag in r.get("tags") or []:
                active_disciplines.add(tag)

        # Check if any gap dimensions overlap with active disciplines
        addressed = []
        for gap in gaps:
            dim = gap.get("dimension", "")
            if dim in active_disciplines:
                addressed.append(gap)

        if addressed:
            logger.info(
                "Insights may address %d gaps: %s",
                len(addressed),
                ", ".join(f"{g.get('cap_slug', '?')}/{g.get('dimension', '?')}" for g in addressed[:5]),
            )
            # Emit for downstream consumers (e.g., briefing generator, notifications)
            from core.engine.events.bus import bus

            await bus.emit(
                "gaps.potentially_addressed",
                {
                    "product_id": product_id,
                    "gaps": [
                        {"capability_slug": g.get("cap_slug", ""), "dimension": g.get("dimension", "")}
                        for g in addressed
                    ],
                },
            )
    except Exception as exc:
        logger.warning("on_insight_created handler failed: %s", exc)


async def on_gap_detected(event_type: str, payload: dict) -> None:
    """Notify when a quality gap is detected (score < 0.4)."""
    try:
        from core.engine.notifications.dispatcher import dispatch

        await dispatch(
            product_id=payload.get("product_id", ""),
            user_id="user:default",
            tier="actionable",
            category="gap_detected",
            title=f"Quality gap: {payload.get('capability_slug', '?')}/{payload.get('dimension', '?')}",
            body=f"Score {payload.get('score', 0):.1f} with {payload.get('gap_count', 0)} gaps.",
            link="/graph",
        )
    except Exception as exc:
        logger.warning("on_gap_detected handler failed: %s", exc)


async def on_initiative_created(event_type: str, payload: dict) -> None:
    """Capture initiative creation as an observation for intelligence tracking."""
    product_id = payload.get("product_id", "")
    title = payload.get("title", "")
    if not product_id or not title:
        return

    try:
        from core.engine.core.db import pool

        async with pool.connection() as db:
            await db.query(
                """
                CREATE observation SET
                    content = $content,
                    observation_type = 'decision',
                    confidence = 0.9,
                    discipline_hint = 'business_logic',
                    domain_hint = 'business_logic',
                    source = 'initiative_created',
                    synthesized = false,
                    created_at = time::now()
                """,
                {
                    "product": product_id,
                    "content": f"Initiative created: {title}. Idea promoted to active work.",
                },
            )
    except Exception as exc:
        logger.warning("on_initiative_created handler failed: %s", exc)


async def on_spec_created(event_type: str, payload: dict) -> None:
    """Log spec creation for intelligence tracking."""
    logger.info(
        "Spec created: source=%s, capability=%s, objective=%s",
        payload.get("source", "?"),
        payload.get("capability_slug", "?"),
        payload.get("objective", "?")[:80],
    )
