"""Decision-shaped recognition classifier.

Haiku-tier LLM classifies whether a conversation turn contains a decision.
Cheap and fast — runs on every turn in the capture pipeline (non-blocking).
"""

from __future__ import annotations

import json
import logging

from core.engine.core.config import settings
from core.engine.core.llm import llm
from core.engine.recognition.models import RecognitionResult

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE = """\
You are watching a conversation between a developer and ACE (an AI partner that
helps build products). Your job is to detect when a DECISION just happened.

A decision is when the user (or user-and-ACE-together) commits to one approach
over an alternative. Examples:
- "Let's go with JWT instead of session cookies"
- "We should use SurrealDB for this — Postgres is overkill"
- "Skip the cache layer for now"
- "Okay, let's do option A"
- "We decided to defer the mobile app to v2"

NOT a decision:
- A question ("Should we use JWT?")
- An observation ("This looks slow")
- A task assignment ("Write the auth module")
- A status update ("The build is passing")
- Casual conversation

Recent conversation turns:
{conversation_context}

Current turn:
"{turn_text}"

Available capabilities in this product:
{capability_list}

Output JSON only — no commentary:
{{
  "is_decision": true or false,
  "confidence": 0.0 to 1.0,
  "decision_type": "architecture" | "convention" | "trade_off" | "direction" | "rejection" | null,
  "extracted_title": "short 5-10 word title" or null,
  "extracted_rationale": "why was this chosen" or null,
  "extracted_alternatives": ["the alternatives that were rejected"],
  "likely_affected_capability": "capability name from the list above" or null,
  "classifier_reasoning": "1-2 sentences why you classified this way"
}}"""


async def classify(
    turn_text: str,
    conversation_context: str = "",
    capabilities: list[str] | None = None,
) -> RecognitionResult:
    """Classify a conversation turn for decision-shaped content.

    Never raises — returns is_decision=False with low confidence on any failure.
    """
    cap_list = "\n".join(f"- {c}" for c in (capabilities or [])) or "(none)"
    prompt = _PROMPT_TEMPLATE.format(
        conversation_context=conversation_context or "(no prior context)",
        turn_text=turn_text,
        capability_list=cap_list,
    )

    try:
        raw = await llm.complete(prompt, model=settings.llm_budget_model, max_tokens=400)
        raw = raw.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)
        return RecognitionResult(
            is_decision=bool(data.get("is_decision", False)),
            confidence=float(data.get("confidence", 0.0)),
            decision_type=data.get("decision_type"),
            extracted_title=data.get("extracted_title") or None,
            extracted_rationale=data.get("extracted_rationale") or None,
            extracted_alternatives=data.get("extracted_alternatives") or [],
            likely_affected_capability=data.get("likely_affected_capability") or None,
            classifier_reasoning=data.get("classifier_reasoning", ""),
        )
    except Exception as exc:
        logger.debug("decision_classifier failed (non-fatal): %s", exc)
        return RecognitionResult(
            is_decision=False,
            confidence=0.0,
            classifier_reasoning=f"classifier error: {type(exc).__name__}",
        )
