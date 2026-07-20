"""Idea capture — parse, classify, and tag a raw idea.

Budget LLM call classifies the idea into domain_path, type, complexity,
generates a title and summary. Returns within 5 seconds. Status: captured.
"""

from __future__ import annotations

import logging

from core.engine.core.config import settings
from core.engine.core.db import parse_one, pool
from core.engine.core.llm import llm
from core.engine.ideas.schemas import IdeaClassification

logger = logging.getLogger(__name__)

CAPTURE_PROMPT = """Classify this idea submitted by a user.

Idea: "{raw_input}"

Return JSON with:
- domain_path: dot-separated domain path (e.g. "technology.engineering", "experience.design-systems")
- type: one of feature, project, process, research, experiment, other
- complexity: one of simple, moderate, complex, ambitious
- title: short descriptive title (5-10 words)
- summary: one paragraph clean description"""


async def capture_idea(
    raw_input: str,
    user_id: str,
    product_id: str,
    workspace_id: str | None = None,
) -> dict:
    """Parse, classify, and store a raw idea.

    Returns:
        The created idea record dict with status='captured'.
    """
    # Budget LLM call to classify
    prompt = CAPTURE_PROMPT.format(raw_input=raw_input[:2000])
    classification = await llm.complete_structured(
        prompt,
        IdeaClassification,
        model=settings.llm_budget_model,
    )

    # Generate tags from discipline (flat string); fall back to splitting old-style domain_path
    _discipline = getattr(classification, "discipline", None)
    _domain_path = getattr(classification, "domain_path", "")
    if _discipline:
        tags = [_discipline]
    elif _domain_path:
        tags = [part for part in _domain_path.split(".") if part]
    else:
        tags = []

    # Persist to DB
    async with pool.connection() as db:
        result = await db.query(
            """
            CREATE idea SET
                product = <record>$product,
                workspace = IF $workspace THEN <record>$workspace ELSE NONE END,
                user = $user,
                raw_input = $raw_input,
                title = $title,
                status = 'captured',
                classification = $classification,
                tags = $tags,
                created_at = time::now()
            """,
            {
                "product": product_id,
                "workspace": workspace_id,
                "user": user_id,
                "raw_input": raw_input,
                "title": classification.title,
                "classification": classification.model_dump(),
                "tags": tags,
            },
        )
        record = parse_one(result)

    record = record if record is not None else {"status": "captured", "title": classification.title}
    return record
