"""Idea activation — convert a ready idea into an initiative.

Takes a ready idea and feeds it into the 5a PM pipeline. Creates an
initiative with source='idea' and source_idea pointing to the idea record.
"""

from __future__ import annotations

import logging

from core.engine.core.db import pool
from core.engine.ideas.state_machine import IdeaStateError, transition

logger = logging.getLogger(__name__)


async def activate_idea(
    idea: dict,
    user_id: str,
    product_id: str,
    workspace_id: str | None = None,
) -> dict:
    """Create an initiative from an incubated idea.

    Raises:
        IdeaStateError: If the idea is not in 'ready' status.
    """
    # Only ready ideas can be activated via this path
    if idea["status"] != "ready":
        raise IdeaStateError(idea["status"], "promoted")
    new_status = transition(idea["status"], "promoted")

    # Emit state change event
    try:
        from core.engine.events.bus import bus

        await bus.emit(
            "idea.state_changed",
            {
                "idea_id": str(idea.get("id", "")),
                "product_id": product_id,
                "old_state": idea["status"],
                "new_state": new_status,
                "title": idea.get("title", ""),
            },
        )
    except Exception:
        pass

    # Build initiative context from incubation data
    brief = idea.get("brief", {})
    connections = idea.get("connections", [])

    context = (
        f"Idea brief: {brief.get('what', '')}\n"
        f"Why: {brief.get('why', '')}\n"
        f"What we know: {brief.get('what_we_know', '')}\n"
        f"Approach: {brief.get('approach', '')}\n"
        f"Effort: {brief.get('effort', '')}\n"
        f"First step: {brief.get('first_step', '')}\n"
        f"Open questions: {brief.get('open_questions', [])}\n"
        f"Risks: {brief.get('risks', [])}\n"
        f"Connections: {len(connections)} related insights"
    )

    async with pool.connection() as db:
        # Transition idea to active
        await db.query(
            "UPDATE <record>$id SET status = $status, activated_at = time::now()",
            {"id": idea["id"], "status": new_status},
        )

        # Create initiative
        result = await db.query(
            """
            CREATE initiative SET
                product = <record>$product,
                user = <record>$user,
                title = $title,
                description = $description,
                source = $source,
                source_idea = $source_idea,
                owner = <record>$user,
                context = $context,
                status = 'planning',
                created_at = time::now()
            """,
            {
                "product": product_id,
                "workspace": workspace_id,
                "user": user_id,
                "title": idea.get("title", "Untitled"),
                "description": brief.get("what", idea.get("raw_input", "")),
                "source": "idea",
                "source_idea": idea["id"],
                "context": context,
            },
        )
        from core.engine.core.db import parse_one

        row = parse_one(result)

        # Create became edge: initiative -> idea (best-effort)
        if row and row.get("id"):
            try:
                from core.engine.graph.edge_writer import create_edge

                await create_edge("became", str(row["id"]), str(idea["id"]), pool=pool)
            except Exception:
                pass

    out = (
        row
        if row
        else {
            "source": "idea",
            "source_idea": idea["id"],
            "title": idea.get("title", "Untitled"),
        }
    )

    # Emit initiative.created event
    try:
        from core.engine.events.bus import bus

        await bus.emit(
            "initiative.created",
            {
                "product_id": product_id,
                "idea_id": str(idea.get("id", "")),
                "initiative_id": str(out.get("id", "")),
                "title": idea.get("title", "Untitled"),
            },
        )
    except Exception:
        pass

    # Capture idea → initiative transition as intelligence signal
    try:
        from datetime import datetime, timezone

        from core.engine.capture.service import capture_service
        from core.engine.capture.watchers import StreamEvent

        title = idea.get("title", "Untitled")
        context_text = idea.get("context", "") or ""
        content = f"Idea promoted to initiative: {title}"
        if context_text:
            content += f"\n\nContext: {str(context_text)[:500]}"

        await capture_service.emit(
            StreamEvent(
                timestamp=datetime.now(timezone.utc),
                event_type="tool_result",
                content=content,
                session_id=str(idea.get("id", "")),
                metadata={
                    "product_id": product_id,
                    "source": "idea_activation",
                    "discipline_hint": "business_logic",
                    "initiative_id": str(out.get("id", "")),
                },
            )
        )
    except Exception as exc:
        logger.debug("Capture emit failed for idea activation %s: %s", idea.get("id"), exc)

    return out
