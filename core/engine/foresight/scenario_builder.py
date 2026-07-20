# engine/foresight/scenario_builder.py
"""Scenario Builder — projects internal signals into probability-weighted future branches.

Sentinel engine (hourly). Reads unbuilt signals from `signal` table.
Asks Sonnet: "given this trend, what are the most likely trajectories?"
Writes to `scenario` + `scenario_branch` tables.

Domain-agnostic: the prompt doesn't assume what domain the capability
represents — it could be software quality, research throughput, legal
coverage, operational readiness, or anything ACE is tracking.
"""

from __future__ import annotations

import json
import logging
import uuid

from core.engine.core.db import parse_rows, pool
from core.engine.core.llm import get_llm
from core.engine.foresight.models import Scenario, ScenarioBranch
from core.engine.sentinel.registry import register_engine

logger = logging.getLogger(__name__)

_SCENARIO_PROMPT = """\
You are ACE, a reasoning partner. An internal signal has been detected about an observed trend.

Signal:
  kind: {kind}
  description: {description}
  confidence: {confidence:.2f}
  trend data: {trend_data}

Project 2-3 distinct scenario branches — what are the realistic consequences if this trend
continues vs. if it is addressed? Stay grounded in observable, measurable outcomes.
Do not assume any particular domain (software, legal, research, operations, etc.).

Output JSON only:
{{
  "branches": [
    {{
      "probability": <float 0.0-1.0>,
      "description": "<one sentence: what this branch predicts>",
      "implication_for_product": "<one sentence: concrete consequence for the initiative>",
      "horizon": "near_term"
    }}
  ]
}}

Probabilities must sum to 1.0. "near_term" = days to 2 weeks. No other text."""


async def _build_scenario(signal_row: dict, product_id: str) -> Scenario | None:
    """Build a scenario tree for a single signal. Returns None on error."""
    llm = get_llm()
    prompt = _SCENARIO_PROMPT.format(
        kind=str(signal_row.get("kind", "unknown")),
        description=str(signal_row.get("description", ""))[:400],
        confidence=float(signal_row.get("confidence", 0.5)),
        trend_data=str(signal_row.get("trend_data", {}))[:200],
    )

    try:
        raw = await llm.complete(prompt, max_tokens=400)
        raw = raw.strip().strip("```json").strip("```").strip()
        data = json.loads(raw)
        branches = [
            ScenarioBranch(
                probability=float(b["probability"]),
                description=str(b["description"]),
                implication_for_product=str(b["implication_for_product"]),
                horizon=str(b.get("horizon", "near_term")),
            )
            for b in data.get("branches", [])
            if b.get("description")
        ]
        if not branches:
            return None
        return Scenario(
            root_signal_id=str(signal_row.get("id", "")),
            kind=str(signal_row.get("kind", "unknown")),
            branches=branches,
        )
    except Exception as exc:
        logger.warning("Scenario build failed for signal %s: %s", signal_row.get("id"), exc)
        return None


async def _write_scenario(scenario: Scenario, product_id: str) -> str:
    """Persist scenario + branches. Returns scenario record ID string."""
    scenario_id = str(uuid.uuid4())
    async with pool.connection() as db:
        await db.query(
            """CREATE type::record('scenario', $id) SET
                product        = <record>$product,
                root_signal_id = $root_signal_id,
                kind           = $kind,
                created_at     = time::now()
            """,
            {
                "id": scenario_id,
                "product": product_id,
                "root_signal_id": scenario.root_signal_id,
                "kind": scenario.kind,
            },
        )
        for branch in scenario.branches:
            branch_id = str(uuid.uuid4())
            await db.query(
                """CREATE type::record('scenario_branch', $id) SET
                    scenario                = type::record('scenario', $scenario_id),
                    probability             = $probability,
                    description             = $description,
                    implication_for_product = $implication,
                    horizon                 = $horizon,
                    created_at              = time::now()
                """,
                {
                    "id": branch_id,
                    "scenario_id": scenario_id,
                    "probability": branch.probability,
                    "description": branch.description,
                    "implication": branch.implication_for_product,
                    "horizon": branch.horizon,
                },
            )
    return scenario_id


@register_engine(
    name="scenario_builder",
    cron="0 * * * *",  # hourly
    description="Project unbuilt internal signals into probability-weighted scenario trees.",
)
async def run_scenario_builder(product_id: str) -> dict:
    """Build scenario trees for all unprocessed signals for this product."""
    results = {"scenarios_built": 0, "errors": 0}

    async with pool.connection() as db:
        signal_result = await db.query(
            """SELECT * FROM signal
               WHERE product = <record>$product
               AND scenario_built = false
               ORDER BY confidence DESC, created_at DESC LIMIT 20""",
            {"product": product_id},
        )
    signals = parse_rows(signal_result)

    for sig in signals:
        scenario = await _build_scenario(sig, product_id)
        if scenario is None:
            results["errors"] += 1
            continue
        try:
            await _write_scenario(scenario, product_id)
            async with pool.connection() as db:
                await db.query(
                    "UPDATE <record>$id SET scenario_built = true",
                    {"id": str(sig["id"])},
                )
            results["scenarios_built"] += 1
        except Exception as exc:
            logger.warning("Failed to persist scenario for signal %s: %s", sig.get("id"), exc)
            results["errors"] += 1

    return results
