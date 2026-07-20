"""Idea incubation — full background processing pipeline.

For each idea in open/legacy status: classify against the intelligence graph,
research feasibility, check for prior work, find related ideas, decompose into
phases if complex, generate a structured brief, and identify connections to
existing insights. Posts results conversationally to the idea's thread.
Only transitions to 'ready' when the brief is substantially complete (5+ fields).
"""

from __future__ import annotations

import logging

from core.engine.core.config import settings
from core.engine.core.db import parse_one, parse_rows, pool
from core.engine.core.llm import llm
from core.engine.ideas.schemas import IncubationBrief
from core.engine.ideas.state_machine import transition

logger = logging.getLogger(__name__)

BRIEF_PROMPT = """Create an executive brief for this idea.

Original idea: "{raw_input}"
Classification: {classification}
Prior related work: {prior_work}
Related ideas in pipeline: {related_ideas}
Related insights: {related_insights}
Qualifying answers: {qualifying_qs}
Decomposed phases: {phases}

Write a brief covering:
1. what — clean description
2. why — why it matters
3. what_we_know — from existing intelligence
4. open_questions — what we'd need to figure out
5. approach — recommended approach
6. effort — effort estimate
7. risks — risks and blockers (array of strings)
8. first_step — first concrete step

Be concise. Scannable in 60 seconds."""

DECOMPOSE_PROMPT = """Decompose this idea into execution phases.

Idea: {summary}
Complexity: {complexity}
Domain: {domain_path}
Prior related work: {prior_work}

For each phase:
- name: Phase name
- description: What this phase does
- archetype: creator|analyst|executor|researcher|advisor|sentinel
- mode: deliberative|reactive|exploratory|procedural|reflective
- estimated_hours: numeric estimate
- depends_on: array of phase indices (0-based)
- requires_human: true if needs human input

Return a JSON array of phase objects."""


async def incubate_idea(idea: dict, product_id: str) -> dict:
    """Run full incubation pipeline on a single idea.

    Returns:
        Dict with brief, phases, connections, status='ready'.
    """
    classification = idea.get("classification", {})
    domain_path = classification.get("domain_path", "")
    complexity = classification.get("complexity", "simple")
    # discipline is a flat string; domain_path kept for backward compat with old DB records
    domain_slug = classification.get("discipline", "") or (domain_path.split(".")[0] if domain_path else "")

    # Step 1: Query prior related work
    prior_work: list[dict] = []
    related_ideas: list[dict] = []
    related_insights: list[dict] = []

    async with pool.connection() as db:
        try:
            result = await db.query(
                """
                SELECT id, description, domain_path, output, created_at
                FROM task
                WHERE product = <record>$product
                  AND domain_path CONTAINS $domain_slug
                ORDER BY created_at DESC
                LIMIT 10
                """,
                {"product": product_id, "domain_slug": domain_slug},
            )
            prior_work = parse_rows(result)
        except Exception as exc:
            logger.warning("Prior work query failed: %s", exc)

        try:
            result = await db.query(
                """
                SELECT id, title, status, classification, created_at
                FROM idea
                WHERE product = <record>$product
                  AND status IN ['ready', 'active', 'incubating']
                  AND id != $current
                ORDER BY created_at DESC
                LIMIT 10
                """,
                {"product": product_id, "current": idea["id"]},
            )
            related_ideas = parse_rows(result)
        except Exception as exc:
            logger.warning("Related ideas query failed: %s", exc)

        try:
            result = await db.query(
                """
                SELECT id, content, insight_type, confidence, domain_path
                FROM insight
                WHERE product = <record>$product
                  AND domain_path CONTAINS $domain_slug
                  AND status = 'active'
                ORDER BY confidence DESC
                LIMIT 10
                """,
                {"product": product_id, "domain_slug": domain_slug},
            )
            related_insights = parse_rows(result)
        except Exception as exc:
            logger.warning("Related insights query failed: %s", exc)

    # Step 2: Decompose into phases if complex
    phases: list[dict] | None = None
    if complexity in ("complex", "ambitious"):
        try:
            prompt = DECOMPOSE_PROMPT.format(
                summary=classification.get("summary", idea["raw_input"])[:500],
                complexity=complexity,
                domain_path=domain_path,
                prior_work=_format_prior_work(prior_work),
            )
            phases = await llm.complete_json(prompt, model=settings.llm_model)
            if not isinstance(phases, list):
                phases = []
        except Exception as exc:
            logger.warning("Phase decomposition failed: %s", exc)
            phases = []

    # Step 3: Generate structured brief
    brief_prompt = BRIEF_PROMPT.format(
        raw_input=idea["raw_input"][:1000],
        classification=str(classification),
        prior_work=_format_prior_work(prior_work),
        related_ideas=_format_related_ideas(related_ideas),
        related_insights=_format_insights(related_insights),
        qualifying_qs=str(idea.get("qualifying_qs", [])),
        phases=str(phases) if phases else "N/A (simple idea)",
    )

    brief = await llm.complete_structured(
        brief_prompt,
        IncubationBrief,
        model=settings.llm_model,
    )

    # Step 4: Build connections
    connections = []
    for insight in related_insights[:10]:
        connections.append(
            {
                "insight_id": str(insight.get("id", "")),
                "content_preview": str(insight.get("content", ""))[:100],
                "relevance": "direct" if domain_slug in str(insight.get("domain_path", "")) else "related",
            }
        )

    # Step 5: Compute effort estimate
    effort_estimate = None
    if phases:
        total_hours = sum(p.get("estimated_hours", 0) or 0 for p in phases)
        effort_estimate = {"total_hours": total_hours, "phase_count": len(phases)}

    # Step 6: Decide whether to transition to 'ready' or stay in current state
    brief_dict = brief.model_dump()
    filled_fields = sum(1 for v in brief_dict.values() if v and v not in ([], "", None))
    # Transition to 'ready' only for legacy-status ideas with a substantially complete brief
    # (5+ of 8 fields). Ideas already in 'open' keep their status — research is posted
    # conversationally and the human decides when to promote.
    current_status = idea["status"]
    if current_status != "open" and filled_fields >= 5:
        new_status = transition(current_status, "ready")
    else:
        new_status = current_status

    # Emit state change event
    if new_status != current_status:
        try:
            from core.engine.events.bus import bus

            await bus.emit(
                "idea.state_changed",
                {
                    "idea_id": str(idea.get("id", "")),
                    "product_id": idea.get("product", ""),
                    "old_state": current_status,
                    "new_state": new_status,
                    "title": idea.get("title", ""),
                },
            )
        except Exception:
            pass

    async with pool.connection() as db:
        await db.query(
            """
            UPDATE <record>$id SET
                status = $status,
                brief = $brief,
                phases = $phases,
                connections = $connections,
                research = $research,
                effort_estimate = $effort_estimate,
                incubated_at = time::now()
            """,
            {
                "id": idea["id"],
                "status": new_status,
                "brief": brief_dict,
                "phases": phases,
                "connections": connections,
                "research": {"prior_work_count": len(prior_work), "related_ideas_count": len(related_ideas)},
                "effort_estimate": effort_estimate,
            },
        )

        # Step 7: Post research findings to the idea's conversation thread
        thread_message = "I did some research on this while you were away.\n\n"
        if brief_dict.get("what"):
            thread_message += f"**What:** {brief_dict['what']}\n\n"
        if brief_dict.get("why"):
            thread_message += f"**Why:** {brief_dict['why']}\n\n"
        if brief_dict.get("approach"):
            thread_message += f"**Approach:** {brief_dict['approach']}\n\n"
        if brief_dict.get("risks"):
            risks = brief_dict["risks"]
            risks_text = ", ".join(risks) if isinstance(risks, list) else str(risks)
            thread_message += f"**Risks:** {risks_text}\n\n"
        thread_message += "What do you think? Want to refine this further or is it ready to promote?"

        try:
            await _post_to_idea_thread(db, str(idea.get("id", "")), product_id, thread_message)
        except Exception as exc:
            logger.warning("Failed to post to idea thread: %s", exc)

    # Emit incubation result into capture pipeline (idea brief = high-signal intelligence)
    try:
        from datetime import datetime, timezone

        from core.engine.capture.service import capture_service
        from core.engine.capture.watchers import StreamEvent

        parts = [f"Idea incubated: {idea.get('title', 'Untitled')}"]
        if brief_dict.get("what"):
            parts.append(f"What: {brief_dict['what']}")
        if brief_dict.get("why"):
            parts.append(f"Why: {brief_dict['why']}")
        if brief_dict.get("approach"):
            parts.append(f"Approach: {brief_dict['approach']}")
        if connections:
            parts.append(
                f"Connects to: {', '.join(c.get('capability', '') for c in connections[:3] if c.get('capability'))}"
            )

        await capture_service.emit(
            StreamEvent(
                timestamp=datetime.now(timezone.utc),
                event_type="tool_result",
                content="\n".join(parts),
                session_id=str(idea.get("id", "")),
                metadata={
                    "product_id": product_id,
                    "source": "idea_incubator",
                    "discipline_hint": "business_logic",
                    "idea_status": new_status,
                },
            )
        )
    except Exception as exc:
        logger.debug("Capture emit failed for idea %s: %s", idea.get("id"), exc)

    return {
        "status": new_status,
        "brief": brief_dict,
        "phases": phases,
        "connections": connections,
        "effort_estimate": effort_estimate,
    }


async def _post_to_idea_thread(db, idea_id: str, product_id: str, message: str) -> None:
    """Post a message from ACE into an idea's linked chat thread."""
    # Find linked session
    session_result = await db.query(
        "SELECT * FROM chat_session WHERE product = <record>$product AND linked_to = $linked AND status = 'active' LIMIT 1",
        {"product": product_id, "linked": idea_id},
    )
    session = parse_one(session_result)

    if session is None:
        # Create session if none exists
        create_result = await db.query(
            """
            CREATE chat_session SET
                workspace = workspace:default,
                user = user:default,
                title = 'ACE Research',
                linked_to = $linked,
                linked_type = 'idea',
                status = 'active',
                message_count = 0,
                created_at = time::now(),
                last_message_at = time::now()
            """,
            {"product": product_id, "linked": idea_id},
        )
        session = parse_one(create_result)

    if session is None:
        return

    session_id = session.get("id")

    # Post message
    await db.query(
        """
        CREATE chat_message SET
            session = $sess,
            role = 'assistant',
            content = $content,
            created_at = time::now()
        """,
        {"sess": session_id, "content": message},
    )

    # Update session metadata
    await db.query(
        "UPDATE <record>$sess SET message_count = message_count + 1, last_message_at = time::now()",
        {"sess": session_id},
    )


def _format_prior_work(tasks: list[dict]) -> str:
    if not tasks:
        return "(none)"
    return "\n".join(f"- {t.get('description', '?')[:100]} ({t.get('domain_path', '?')})" for t in tasks[:5])


def _format_related_ideas(ideas: list[dict]) -> str:
    if not ideas:
        return "(none)"
    return "\n".join(f"- {i.get('title', '?')} (status: {i.get('status', '?')})" for i in ideas[:5])


def _format_insights(insights: list[dict]) -> str:
    if not insights:
        return "(none)"
    return "\n".join(
        f"- [{i.get('insight_type', '?')}] {str(i.get('content', ''))[:100]} (conf: {i.get('confidence', '?')})"
        for i in insights[:5]
    )
