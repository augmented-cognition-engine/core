# engine/intelligence/ab_judge.py
from __future__ import annotations

import json
import logging

from core.engine.core.llm import get_llm
from core.engine.orchestration import orchestrate
from core.engine.orchestration.request import OrchestrationRequest

logger = logging.getLogger(__name__)

_JUDGE_PROMPT = """\
Compare two AI assistant outputs for the same task. Determine which is better.

Task: {description}

Output A (with intelligence context injected):
{treatment_output}

Output B (no intelligence context):
{control_output}

Evaluate on: (1) factual correctness, (2) conciseness, (3) actionability.
Respond with exactly one JSON object (no other text):
{{"preference": "A" | "B" | "tie", "rationale": "one sentence"}}
"""


async def run_shadow_comparison(
    description: str,
    classification: dict,
    product_id: str,
    treatment_output: str,
) -> dict | None:
    """Run control task and compare against treatment output via Haiku judge.

    Returns None on any failure — caller must handle gracefully.
    """
    try:
        from core.engine.core.config import settings

        shadow_req = OrchestrationRequest(
            description=description,
            product_id=product_id,
            workspace_id="workspace:default",
            user_id="user:ab_shadow",
            source="direct",
            shadow_run=True,
            classification_override=classification,
            intelligence_override={
                "insights": [],
                "specialty_insights": [],
                "org_insights": [],
                "total_count": 0,
            },
            persist_task=False,
            persist_events=False,
            run_post_hooks=False,
        )
        shadow_result = await orchestrate(shadow_req)
        control_output = shadow_result.output or ""

        llm = get_llm()
        prompt = _JUDGE_PROMPT.format(
            description=description[:300],
            treatment_output=treatment_output[-1500:],
            control_output=control_output[-1500:],
        )
        raw = await llm.complete(prompt, model=settings.llm_budget_model, max_tokens=150)

        start = raw.rfind("{")
        end = raw.rfind("}")
        if start == -1 or end == -1 or end < start:
            logger.warning("ab_judge: malformed JSON from judge: %r", raw[:100])
            return None

        parsed = json.loads(raw[start : end + 1])
        pref_raw = parsed.get("preference", "tie")
        if pref_raw == "A":
            judge_preference = "treatment"
        elif pref_raw == "B":
            judge_preference = "control"
        else:
            judge_preference = "tie"

        return {
            "judge_preference": judge_preference,
            "judge_rationale": str(parsed.get("rationale", ""))[:500],
        }

    except Exception as exc:
        logger.warning("A/B shadow comparison failed (non-fatal): %s", exc)
        return None
