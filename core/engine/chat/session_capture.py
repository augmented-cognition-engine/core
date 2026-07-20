# engine/chat/session_capture.py
"""Session capture — extract observations from archived chat sessions.

When a session is archived, uses the budget LLM to extract structured
observations (corrections, decisions, preferences) and writes them to the
observation table. These flow through the normal capture pipeline on the
next sentinel cycle.
"""

from __future__ import annotations

import logging

from core.engine.core.config import settings
from core.engine.core.db import pool
from core.engine.core.llm import llm

logger = logging.getLogger(__name__)

MAX_OBSERVATIONS = 10
MIN_MESSAGES = 2
MAX_CONTENT_LENGTH = 500

EXTRACTION_PROMPT = """Extract key observations from this chat session transcript.

For each observation, classify as one of:
- decision: user made or stated a decision (PRIORITIZE — extract ALL decisions)
- correction: user corrected the AI's output
- preference: user expressed a preference for approach/style/convention
- pattern: recurring pattern observed across the conversation
- learning: factual knowledge surfaced during the conversation

IMPORTANT: Decisions are the highest priority. Extract every decision you find,
including architecture choices, trade-off resolutions, and rejected alternatives.
For decisions, include what was chosen AND what was rejected if mentioned.

Return a JSON array of observations (max {max_obs}):
[{{"observation_type": "...", "content": "...", "domain_path": "...", "confidence": 0.0-1.0}}]

If no observations are worth extracting, return an empty array: []

Transcript:
{transcript}"""


async def extract_session_observations(
    session_id: str,
    product_id: str,
) -> list[dict]:
    """Extract observations from an archived chat session.

    Returns list of observation dicts written to DB. Non-blocking — designed
    to be called via asyncio.create_task().
    """
    try:
        # Load messages
        async with pool.connection() as db:
            result = await db.query(
                """
                SELECT role, content, created_at FROM chat_message
                WHERE session = <record>$sess
                ORDER BY created_at ASC
                """,
                {"sess": session_id},
            )
            rows = result[0] if result and isinstance(result[0], list) else (result or [])
            messages = [r for r in rows if isinstance(r, dict)]

        if len(messages) < MIN_MESSAGES:
            logger.debug("Session %s has < %d messages, skipping capture", session_id, MIN_MESSAGES)
            return []

        # Build transcript
        transcript_lines = []
        for msg in messages:
            role = msg.get("role", "user")
            content = str(msg.get("content", ""))[:MAX_CONTENT_LENGTH]
            transcript_lines.append(f"{role}: {content}")
        transcript = "\n".join(transcript_lines)

        # Extract observations via budget LLM
        prompt = EXTRACTION_PROMPT.format(max_obs=MAX_OBSERVATIONS, transcript=transcript)
        observations_raw = await llm.complete_json(prompt, model=settings.llm_budget_model)

        if not isinstance(observations_raw, list):
            observations_raw = observations_raw.get("observations", [])

        # Write to observation table
        written = []
        async with pool.connection() as db:
            for obs in observations_raw[:MAX_OBSERVATIONS]:
                if not isinstance(obs, dict) or not obs.get("content"):
                    continue
                await db.query(
                    """
                    CREATE observation SET
                        product = <record>$product,
                        observation_type = $type,
                        content = $content,
                        domain_path = $domain_path,
                        confidence = $confidence,
                        source = 'chat_session',
                        source_session = $sess,
                        created_at = time::now()
                    """,
                    {
                        "product": product_id,
                        "type": obs.get("observation_type", "learning"),
                        "content": obs["content"],
                        "domain_path": obs.get("domain_path", ""),
                        "confidence": max(0.0, min(1.0, float(obs.get("confidence", 0.5)))),
                        "sess": session_id,
                    },
                )
                written.append(obs)

        logger.info(
            "Session capture: extracted %d observations from session %s",
            len(written),
            session_id,
        )
        return written

    except Exception as exc:
        logger.warning("Session capture failed for %s: %s", session_id, exc)
        return []
