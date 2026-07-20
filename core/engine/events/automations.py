"""Built-in automation handlers — registered on app startup.

These handlers react to events and trigger notifications or engine runs.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_CRITICAL_GAP_THRESHOLD = 0.2
_MAX_IDEAS_PER_RUN = 3


async def _create_ideas_for_critical_gaps(product_id: str, db) -> None:
    """Query capability_quality for critical gaps and create idea records.

    Reads the worst-scoring capabilities (score < 0.2, up to 3) and writes
    a pre-classified idea for each so they surface in the conductor work queue.
    Non-fatal — any failure is swallowed.
    """
    try:
        from core.engine.core.db import parse_rows

        rows = parse_rows(
            await db.query(
                """SELECT capability_slug, dimension, score, gaps
                   FROM capability_quality
                   WHERE product = <record>$product
                     AND score < $threshold
                   ORDER BY score ASC
                   LIMIT $limit""",
                {
                    "product": product_id,
                    "threshold": _CRITICAL_GAP_THRESHOLD,
                    "limit": _MAX_IDEAS_PER_RUN,
                },
            )
        )

        for row in rows[:_MAX_IDEAS_PER_RUN]:
            slug = row.get("capability_slug", "unknown")
            dimension = row.get("dimension", "unknown")
            score = row.get("score", 0.0)
            gaps = row.get("gaps") or []
            gap_summary = "; ".join(gaps[:3]) if gaps else "no details"

            title = f"Fix {dimension} gap in {slug}"
            raw_input = (
                f"{dimension} quality gap detected in capability '{slug}' (score {score:.2f}). Issues: {gap_summary}"
            )

            await db.query(
                """CREATE idea SET
                   product = <record>$product,
                   user = 'system',
                   raw_input = $raw_input,
                   title = $title,
                   status = 'captured',
                   classification = $classification,
                   tags = $tags,
                   created_at = time::now()""",
                {
                    "product": product_id,
                    "raw_input": raw_input,
                    "title": title,
                    "classification": {
                        "domain_path": f"quality.{dimension}",
                        "type": "project",
                        "complexity": "moderate",
                        "title": title,
                        "summary": raw_input,
                    },
                    "tags": [dimension, "gap", slug, "sentinel"],
                },
            )
    except Exception as exc:
        logger.warning("_create_ideas_for_critical_gaps failed (non-fatal): %s", exc)


async def on_idea_ready(event_type: str, payload: dict) -> None:
    """Notify when an idea reaches 'ready' state."""
    if payload.get("new_state") != "ready":
        return

    try:
        from core.engine.notifications.dispatcher import dispatch

        await dispatch(
            product_id=payload.get("product_id", ""),
            user_id="user:default",
            tier="actionable",
            category="idea_ready",
            title=f"Idea ready for activation: {payload.get('title', 'Untitled')}",
            body=f"Idea {payload.get('idea_id', '?')} is ready to become an initiative.",
            link="/ideas",
        )
    except Exception as exc:
        logger.warning("on_idea_ready handler failed: %s", exc)


async def on_maturation_expert(event_type: str, payload: dict) -> None:
    """Notify when a specialty reaches Expert phase, and broadcast insights cross-product."""
    if payload.get("new_phase") not in ("expert", "authoritative"):
        return

    product_id = payload.get("product_id", "")
    specialty_slug = payload.get("slug") or payload.get("node_id", "")

    try:
        from core.engine.notifications.dispatcher import dispatch

        await dispatch(
            product_id=product_id,
            user_id="user:default",
            tier="informational",
            category="maturation_milestone",
            title=f"Specialty reached {payload.get('new_phase', 'expert')} phase",
            body=f"{payload.get('node_id', '?')} has matured to {payload.get('new_phase', 'expert')}.",
        )
    except Exception as exc:
        logger.warning("on_maturation_expert handler failed: %s", exc)

    # Cross-product specialty broadcast: propagate high-confidence insights
    # to other products in the same ecosystem.
    if product_id and specialty_slug:
        try:
            from core.engine.core.db import parse_rows, pool
            from core.engine.intelligence.specialty_broadcast import broadcast_specialty

            async with pool.connection() as db:
                insight_rows = parse_rows(
                    await db.query(
                        """SELECT id, content, confidence, tier FROM insight
                           WHERE product = <record>$product
                             AND status = 'active'
                             AND confidence >= 0.8
                             AND (source_domain = $slug OR tags CONTAINS $slug)
                           ORDER BY confidence DESC
                           LIMIT 20""",
                        {"product": product_id, "slug": specialty_slug},
                    )
                )
                if insight_rows:
                    count = await broadcast_specialty(
                        db=db,
                        source_product_id=product_id,
                        specialty_slug=specialty_slug,
                        insights=insight_rows,
                    )
                    if count:
                        logger.info(
                            "Specialty broadcast: %s propagated %d insights across ecosystem",
                            specialty_slug,
                            count,
                        )
        except Exception as exc:
            logger.warning("specialty broadcast failed (non-fatal): %s", exc)


async def on_high_confidence_conflict(event_type: str, payload: dict) -> None:
    """Alert on conflicts between high-confidence insights."""
    try:
        from core.engine.notifications.dispatcher import dispatch

        await dispatch(
            product_id=payload.get("product_id", ""),
            user_id="user:default",
            tier="actionable",
            category="conflict_detected",
            title="Intelligence conflict detected",
            body=f"Conflict {payload.get('conflict_id', '?')} needs resolution.",
            link="/conflicts",
        )
    except Exception as exc:
        logger.warning("on_high_confidence_conflict handler failed: %s", exc)


async def on_specialty_emerged(event_type: str, payload: dict) -> None:
    """Trigger specialty deepener when a new specialty emerges."""
    try:
        from core.engine.notifications.dispatcher import dispatch

        await dispatch(
            product_id=payload.get("product_id", ""),
            user_id="user:default",
            tier="informational",
            category="specialty_emerged",
            title=f"New specialty emerged: {payload.get('slug', '?')}",
            body=f"Specialty {payload.get('slug', '?')} emerged from {payload.get('insight_count', 0)} insights.",
        )
    except Exception as exc:
        logger.warning("on_specialty_emerged handler failed: %s", exc)


async def on_engine_run_completed(event_type: str, payload: dict) -> None:
    """Trigger briefing generation when sentinel engines complete, if last briefing is stale (>20h)."""
    from datetime import datetime, timedelta, timezone

    product_id = payload.get("product_id", "")
    if not product_id:
        return

    try:
        from core.engine.core.db import parse_one, pool

        async with pool.connection() as db:
            last_result = await db.query(
                "SELECT created_at FROM briefing WHERE product = <record>$product ORDER BY created_at DESC LIMIT 1",
                {"product": product_id},
            )
            last_row = parse_one(last_result)
            last_at = last_row.get("created_at") if last_row else None

        cutoff = datetime.now(timezone.utc) - timedelta(hours=20)
        if last_at and last_at > cutoff:
            return  # fresh briefing exists — skip

        from core.engine.sentinel.engines.briefing import run_briefing_generator

        await run_briefing_generator(product_id, budget=5)
        logger.info("Briefing auto-generated after engine_run.completed (engine=%s)", payload.get("engine"))
    except Exception as exc:
        logger.warning("on_engine_run_completed briefing trigger failed: %s", exc)

    # Gap → idea queue: when gap_analyzer runs, surface critical gaps as work items
    if payload.get("engine") == "gap_analyzer":
        try:
            from core.engine.core.db import pool

            async with pool.connection() as db:
                await _create_ideas_for_critical_gaps(product_id, db)
        except Exception as exc:
            logger.warning("gap_analyzer idea creation failed (non-fatal): %s", exc)


async def on_briefing_generated(event_type: str, payload: dict) -> None:
    """Push briefing notification when a new briefing is generated."""
    try:
        from core.engine.notifications.dispatcher import dispatch

        period = payload.get("period", "")
        summary = payload.get("summary", "")
        body = f"Intelligence briefing for {period}" + (f": {summary}" if summary else "")

        await dispatch(
            product_id=payload.get("product_id", ""),
            user_id="user:default",
            tier="actionable",
            category="briefing",
            title=f"Briefing ready: {period}",
            body=body,
            source_record=payload.get("briefing_id"),
            link="/briefings",
        )
    except Exception as exc:
        logger.warning("on_briefing_generated handler failed: %s", exc)


def register_builtin_handlers() -> None:
    """Register all built-in automation handlers with the event bus.

    Respects ACE_DISABLED_EVENTS env var: comma-separated list of event types
    to skip registering (useful for test environments or partial deployments).
    Example: ACE_DISABLED_EVENTS=gate.pending,gate.approved
    """
    import os

    disabled_events: frozenset[str] = frozenset(
        e.strip() for e in os.environ.get("ACE_DISABLED_EVENTS", "").split(",") if e.strip()
    )
    if disabled_events:
        logger.info("Event handler registration skipping disabled events: %s", sorted(disabled_events))

    from core.engine.events.bus import bus

    def _register(event_type: str, handler) -> None:
        if event_type in disabled_events:
            logger.debug("Skipping disabled handler: %s → %s", event_type, handler.__name__)
            return
        bus.on(event_type, handler)

    from core.engine.events.live_handlers import (
        on_agent_state_changed,
        on_edit_conflict_detected,
    )
    from core.engine.events.product_handlers import (
        on_gap_detected,
        on_initiative_created,
        on_insight_created,
        on_spec_created,
        on_task_completed,
    )

    # Intelligence handlers
    _register("engine_run.completed", on_engine_run_completed)
    _register("idea.state_changed", on_idea_ready)
    _register("maturation.phase_changed", on_maturation_expert)
    _register("insight.conflict", on_high_confidence_conflict)
    _register("specialty.emerged", on_specialty_emerged)
    _register("briefing.generated", on_briefing_generated)

    # Product feedback loop handlers
    _register("task.completed", on_task_completed)
    _register("insight.created", on_insight_created)
    _register("gap.detected", on_gap_detected)
    _register("initiative.created", on_initiative_created)
    _register("spec.created", on_spec_created)

    # LIVE layer handlers
    _register("agent.state_changed", on_agent_state_changed)
    _register("edit.conflict_detected", on_edit_conflict_detected)

    from core.engine.events.gate_handlers import (
        on_gate_approved,
        on_gate_auto_approved,
        on_gate_pending,
        on_gate_rejected,
    )

    # Gate lifecycle handlers
    _register("gate.pending", on_gate_pending)
    _register("gate.approved", on_gate_approved)
    _register("gate.rejected", on_gate_rejected)
    _register("gate.auto_approved", on_gate_auto_approved)

    # Proactive intelligence — synthesizes cross-discipline signals on key events
    from core.engine.synthesis.trigger import SynthesisTrigger

    synthesis_trigger = SynthesisTrigger(bus=bus)
    synthesis_trigger.register()

    handlers = bus.list_handlers()
    total = sum(len(v) for v in handlers.values())
    logger.info("Registered %d event handlers across %d event types", total, len(handlers))
