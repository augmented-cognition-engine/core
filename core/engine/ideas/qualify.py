"""Idea qualification — determine if clarifying questions are needed.

Evaluates whether the idea is clear enough to incubate. If ambiguous,
generates 1-2 targeted questions (never more). Non-blocking: the idea
sits in 'qualifying' status until the user answers.
"""

from __future__ import annotations

import logging

from core.engine.core.config import settings
from core.engine.core.db import parse_one, pool
from core.engine.core.llm import llm
from core.engine.ideas.schemas import QualificationResult
from core.engine.ideas.state_machine import IdeaStateError, transition

logger = logging.getLogger(__name__)

QUALIFY_PROMPT = """Idea: "{raw_input}"

Can this idea be meaningfully incubated as-is, or do you need 1-2 clarifying
questions first?

Rules:
- If the intent is clear, say "ready" — don't ask unnecessary questions
- If truly ambiguous, ask at most 2 short questions
- Questions should be answerable in one sentence each

Return JSON:
{{"status": "ready|needs_questions", "questions": ["...", "..."]}}"""


async def qualify_idea(idea: dict, product_id: str) -> dict:
    """Determine if the idea needs clarification before incubation.

    Returns:
        Dict with status ('ready' or 'open') and questions (list or None).

    Raises:
        IdeaStateError: If the idea cannot be qualified (e.g., already promoted).
    """
    # Guard: only open/captured ideas can be qualified
    current = idea.get("status", "")
    if current not in ("open", "captured", "qualifying", "incubating", "proposed"):
        raise IdeaStateError(current, "ready")

    prompt = QUALIFY_PROMPT.format(raw_input=idea["raw_input"][:2000])
    qualification = await llm.complete_structured(
        prompt,
        QualificationResult,
        model=settings.llm_budget_model,
    )

    if qualification.status == "ready":
        # Per QUALIFY_PROMPT contract: "ready" means the LLM judged the idea
        # clear enough to incubate without clarifying questions — NOT that
        # the idea should skip enrichment entirely. The prior fast-path
        # transitioned status directly without producing a brief, which
        # left ideas surfaced as "ready for review" with no review material.
        # Run incubation inline so reaching `ready` always implies a brief
        # is present.
        async with pool.connection() as db:
            await db.query(
                "UPDATE <record>$id SET qualified_at = time::now()",
                {"id": idea["id"]},
            )
        from core.engine.ideas.incubate import incubate_idea

        try:
            incubated = await incubate_idea(idea, product_id)
            return {"status": incubated.get("status", idea["status"]), "questions": None}
        except Exception as exc:
            # If incubation fails the idea must NOT silently land in 'ready'
            # without a brief. Keep it in its current status so the cron
            # retries overnight; surface the failure to the caller.
            logger.warning("Inline incubation failed for %s; deferring to cron: %s", idea.get("id"), exc)
            return {"status": idea["status"], "questions": None, "incubation_deferred": True}

    # Needs clarification — move to qualifying with questions attached
    new_status = transition(idea["status"], "qualifying")
    questions = [{"q": q, "a": None} for q in qualification.questions]

    async with pool.connection() as db:
        await db.query(
            "UPDATE <record>$id SET status = $status, qualifying_qs = $questions",
            {"id": idea["id"], "status": new_status, "questions": questions},
        )

    return {"status": new_status, "questions": qualification.questions}


async def answer_qualifying_questions(idea_id: str, answers: list[str]) -> dict:
    """Record answers to qualifying questions and transition to incubating."""
    async with pool.connection() as db:
        fetch_result = await db.query(
            "SELECT qualifying_qs, status FROM $id",
            {"id": idea_id},
        )
        idea = parse_one(fetch_result)
        if idea is None:
            raise ValueError(f"Idea {idea_id} not found")
        qs = idea.get("qualifying_qs", [])

        # Pair answers with questions
        for i, answer in enumerate(answers):
            if i < len(qs):
                qs[i]["a"] = answer

        new_status = transition(idea.get("status", "open"), "ready")

        result = await db.query(
            "UPDATE <record>$id SET status = $status, qualifying_qs = $qs",
            {"id": idea_id, "status": new_status, "qs": qs},
        )
        updated = parse_one(result)

    return updated if updated is not None else {"id": idea_id, "status": new_status}
